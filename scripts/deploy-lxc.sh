#!/usr/bin/env bash
#
# HCC Deployment-Script fuer den unprivilegierten Debian-LXC (R0 Foundation).
#
# Aufruf (als root IM LXC):
#   sudo scripts/deploy-lxc.sh /pfad/zu/hcc-checkout
#   sudo scripts/deploy-lxc.sh /pfad/zu/hcc-checkout --start
#
# Eigenschaften:
# - idempotent: jede Stufe wird nur ausgefuehrt, wenn noetig
# - keine Secrets im Repository; /etc/hcc/hcc.env wird lokal erzeugt (0640)
# - keine produktiven Aenderungen OUTSIDE dieses LXC
# - Frontend-Build nur, wenn Node.js vorliegt (sonst klare Warnung)
#
# Erwartete Layout-Konventionen (docs/DEPLOYMENT_PLAYBOOK.md Abschnitt 5/6):
#   /opt/hcc/releases/<commit-sha>/{backend,frontend}
#   /opt/hcc/current  -> Symlink auf aktive Release
#   /etc/hcc/hcc.env  (0640 root:hcc), /etc/hcc/secrets.env (optional)
#   /var/lib/hcc, /var/log/hcc

set -euo pipefail

SRC="${1:-}"
START_ON_FINISH=0
if [ "$#" -ge 2 ] && [ "$2" = "--start" ]; then START_ON_FINISH=1; fi

if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
    echo "Usage: sudo $0 <repo-checkout-dir> [--start]" >&2
    exit 1
fi
SRC="$(cd "$SRC" && pwd)"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: Dieses Skript muss als root im LXC ausgefuehrt werden." >&2
    exit 1
fi
if [ ! -f /etc/debian_version ]; then
    echo "ERROR: Unerwartetes Betriebssystem (Debian erwartet)." >&2
    exit 1
fi

log() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
log "Stufe 1/7: Basis-Pakete (idempotent)"
# Node.js NICHT systemweit installieren: Version muss zu frontend/package.json
# (engines >= 20.19) und Lockfile passen; bewusst manuell, nach Pruefung.
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    ca-certificates git nginx postgresql python3 python3-venv openssl

# ---------------------------------------------------------------------------
log "Stufe 2/7: uv (Version-Manager fuer Python) — ohne curl|sh"
UV_BIN=""
if have uv; then
    UV_BIN="$(command -v uv)"
else
    if [ ! -x /opt/hcc/tools/uv/bin/uv ]; then
        mkdir -p /opt/hcc/tools
        python3 -m venv /opt/hcc/tools/uv
        /opt/hcc/tools/uv/bin/pip install --quiet --upgrade pip
        /opt/hcc/tools/uv/bin/pip install --quiet uv
    fi
    UV_BIN=/opt/hcc/tools/uv/bin/uv
fi
echo "uv: $UV_BIN ($($UV_BIN --version))"

# ---------------------------------------------------------------------------
log "Stufe 3/7: Service-Identitaet und Verzeichnisse"
if ! id -u hcc >/dev/null 2>&1; then
    useradd --system --home-dir /var/lib/hcc --shell /usr/sbin/nologin hcc
fi
mkdir -p /opt/hcc/releases /etc/hcc /var/lib/hcc /var/log/hcc
chown -R hcc:hcc /var/lib/hcc /var/log/hcc /opt/hcc

# ---------------------------------------------------------------------------
log "Stufe 4/7: PostgreSQL — dedizierter User (kein Superuser)"
PG_PASS_FILE=/etc/hcc/.pg_password
if [ ! -f "$PG_PASS_FILE" ]; then
    openssl rand -hex 24 > "$PG_PASS_FILE"
    chmod 600 "$PG_PASS_FILE"
fi
PG_PASS="$(cat "$PG_PASS_FILE")"
# Peer-Auth: psql-Pruefungen laufen als postgres-User, nie als root.
ROLE_EXISTS="$(su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='hcc'\"")"
if [ "$ROLE_EXISTS" != "1" ]; then
    su - postgres -c "psql -c \"CREATE ROLE hcc LOGIN PASSWORD '${PG_PASS}'\""
fi
DB_EXISTS="$(su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='hcc'\"")"
if [ "$DB_EXISTS" != "1" ]; then
    su - postgres -c "createdb --owner=hcc hcc"
fi
# PostgreSQL bleibt nur fuer lokale/Socket-Verbindungen relevant (Default).
echo "PG-Rolle 'hcc' und Datenbank 'hcc' vorhanden."

# ---------------------------------------------------------------------------
log "Stufe 5/7: Release-Deployment nach /opt/hcc/releases/<commit>"
if ! git -C "$SRC" rev-parse --verify HEAD >/dev/null 2>&1; then
    echo "ERROR: $SRC ist kein Git-Checkout." >&2
    exit 1
fi
COMMIT="$(git -C "$SRC" rev-parse HEAD)"
BRANCH="$(git -C "$SRC" rev-parse --abbrev-ref HEAD)"
RELEASE_DIR="/opt/hcc/releases/${COMMIT}"

if [ ! -d "$RELEASE_DIR" ]; then
    mkdir -p "$RELEASE_DIR"
    # Sauberer Snapshot OHNE .git
    git -C "$SRC" archive --format=tar HEAD | tar -x -C "$RELEASE_DIR"
fi

# --- Backend: Venv aus uv.lock (reproduzierbar) ---
if [ ! -x "$RELEASE_DIR/backend/.venv/bin/python" ]; then
    (cd "$RELEASE_DIR/backend" && "$UV_BIN" sync --frozen)
fi

# --- Frontend: Build nur mit vorhandenem Node.js ---
if [ ! -d "$RELEASE_DIR/frontend/dist" ]; then
    if have node; then
        echo "Node: $(node --version)"
        (cd "$RELEASE_DIR/frontend" && npm install --no-audit --no-fund && npm run build)
    else
        echo "WARNUNG: Node.js fehlt — Frontend-Build ausgesetzt." >&2
        echo "WARNUNG: nginx liefert bis dahin kein SPA. Node.js >= 20.19" >&2
        echo "WARNUNG: (geprueftes Repository) installieren und neu ausfuehren." >&2
    fi
fi

# --- Current-Symlink (atomar) ---
LINK_TMP="/opt/hcc/current.tmp.$$"
ln -sfn "$RELEASE_DIR" "$LINK_TMP"
if [ -e /opt/hcc/current ] || [ -L /opt/hcc/current ]; then
    rm /opt/hcc/current
fi
mv "$LINK_TMP" /opt/hcc/current
chown -R hcc:hcc "$RELEASE_DIR"
echo "Aktive Release: $RELEASE_DIR (Branch: $BRANCH)"

# ---------------------------------------------------------------------------
log "Stufe 6/7: Konfiguration /etc/hcc/hcc.env (0640, niemals im Repo)"
ENV_FILE=/etc/hcc/hcc.env
if [ ! -f "$ENV_FILE" ]; then
    # Basis: .env.example, dann Produktionswerte ueberschreiben.
    sed -e 's/^HCC_ENVIRONMENT=.*/HCC_ENVIRONMENT=production/' \
        -e 's|^HCC_DATABASE_URL=.*|HCC_DATABASE_URL=postgresql+psycopg://hcc:'"${PG_PASS}"'@127.0.0.1:5432/hcc|' \
        -e 's/^HCC_COOKIE_SECURE=.*/HCC_COOKIE_SECURE=true/' \
        -e 's/^HCC_GIT_COMMIT=.*/HCC_GIT_COMMIT='"${COMMIT}"'/' \
        "$SRC/.env.example" > "$ENV_FILE"
    # Einmaliger Bootstrap-Token (mind. 16 Zeichen, Zufall, nur hier)
    if grep -q '^HCC_BOOTSTRAP_TOKEN=' "$ENV_FILE"; then
        sed -i 's/^HCC_BOOTSTRAP_TOKEN=.*/HCC_BOOTSTRAP_TOKEN='"$(openssl rand -hex 24)"'/' "$ENV_FILE"
    else
        echo "HCC_BOOTSTRAP_TOKEN=$(openssl rand -hex 24)" >> "$ENV_FILE"
    fi
    chmod 640 "$ENV_FILE"
    chown root:hcc "$ENV_FILE"
    echo "Erstellt: $ENV_FILE (Bootstrap-Token einmalig generiert, nur in dieser Datei)."
else
    echo "Vorhanden (unveraendert): $ENV_FILE"
fi
# Secrets-Datei nur erwaehnen; Inhalt wird nie hier erzeugt.
if [ ! -f /etc/hcc/secrets.env ]; then
    echo "Hinweis: /etc/hcc/secrets.env fehlt (optional, Adapter-Secrets)."
fi

# ---------------------------------------------------------------------------
log "Stufe 7/7: Systemdienst + nginx"
install -m 644 "$SRC/deploy/systemd/hcc-api.service" /etc/systemd/system/hcc-api.service
systemctl daemon-reload
systemctl enable hcc-api.service

install -d /etc/nginx/sites-available /etc/nginx/sites-enabled
install -m 644 "$SRC/deploy/nginx/hcc.conf" /etc/nginx/sites-available/hcc.conf
ln -sfn /etc/nginx/sites-available/hcc.conf /etc/nginx/sites-enabled/hcc.conf
nginx -t
if systemctl is-active --quiet nginx; then
    systemctl reload nginx
else
    systemctl start nginx
fi

if [ "$START_ON_FINISH" -eq 1 ]; then
    echo "Starte hcc-api.service (laeuft alembic upgrade head als ExecStartPre) ..."
    systemctl restart hcc-api.service
    sleep 3
    systemctl --no-pager status hcc-api.service --lines=15 || true
    curl -fsS http://127.0.0.1:8000/api/v1/health/live || echo "WARNUNG: Live-Check schlaegig."
fi

echo
echo "Deployment abgeschlossen."
echo "  API (Loopback):    http://127.0.0.1:8000/api/v1/health/live"
echo "  nginx (Serve):     http://127.0.0.1:8080  (Tailscale Serve davor fuer TLS)"
echo "  Nachstes:          einmalig Admin per POST /api/v1/auth/bootstrap anlegen"
echo "                     (HCC_BOOTSTRAP_TOKEN aus /etc/hcc/hcc.env)."
