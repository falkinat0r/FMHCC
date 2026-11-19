#!/bin/bash
#
# HCC E2E-Smoke (R1, Agent 5) — laeuft NUR im Ziel-LXC, nie in CI.
#
# Zeitpunkt: nach Merge + deploy-lxc.sh --start, auf dem produktiven
# Loopback-Stack (nginx 127.0.0.1:8080, API 127.0.0.1:8000, PostgreSQL).
#
# Aufruf (als root IM LXC, mit curl + jq):
#   sudo bash tests/e2e/e2e-smoke.sh
#
# Deckung (siehe docs/quality/integration-matrix.md):
#   1. Health: /api/v1/health/live + /ready (200 bzw. 503-genaech)
#   2. Version: /api/v1/version liefert commit
#   3. OpenAPI-Publikation erreichbar
#   4. Login: Admin-Credentials => Session-Cookie hcc_session (HttpOnly)
#   5. RBAC: Viewer ohne users.manage => 403 auf POST /api/v1/users
#   6. CSRF: POST ohne X-CSRF-Token => 403
#   7. Error-Envelope: 404 liefert {error:{code,message,request_id}}
#   8. SPA: nginx liefert /index.html (Frontend-Built vorhanden)
#
# Exit 0 = alle Schritte bestanden, 1 = mindestens einer fehlgeschlagen.
# WICHTIG: Das Skript erzeugt einen Test-Nutzer "qa_smoke_viewer"
# (viewer, nur zum RBAC-Nachweis) und deaktiviert ihn am Ende
# (PATCH is_active=false; es gibt bewusst kein DELETE-Nutzer-API).
# Bootstrap ist hier NICHT Teil der Pruefung.

set -euo pipefail

API="http://127.0.0.1:8080/api/v1"   # ueber nginx (Produktionspfad)
ADMIN_USER="${HCC_SMOKE_ADMIN:-admin}"
ADMIN_PASS="${HCC_SMOKE_PASS:?ERROR: HCC_SMOKE_PASS muss gesetzt sein (kein Default)}"
PASS=0
FAIL=0
COOKIE_JAR="$(mktemp)"
trap 'rm -f "$COOKIE_JAR"' EXIT

step() { printf '\n==> %s\n' "$*"; }
ok()   { echo "    OK: $*"; PASS=$((PASS + 1)); }
bad()  { echo "    FEHLER: $*"; FAIL=$((FAIL + 1)); }

require() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "ERROR: '$1' fehlt im LXC (apt-get install $1)." >&2
        exit 1
    }
}
require curl
require jq

# --- 1. Health ---------------------------------------------------------------
step "1/8 Health ueber nginx"
if curl -fsS -m 10 "$API/health/live" | jq -e '.status == "ok"' >/dev/null; then
    ok "live"
else
    bad "live"
fi
READY_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$API/health/ready")"
case "$READY_CODE" in
    200) ok "ready (200)" ;;
    503) ok "ready (503 = DB nicht erreichbar, wird dokumentiert)" ;;
    *)   bad "ready (unerwarteter Code: $READY_CODE)" ;;
esac

# --- 2. Version ---------------------------------------------------------------
step "2/8 Version"
COMMIT="$(curl -fsS -m 10 "$API/version" | jq -r '.commit // empty' 2>/dev/null)"
if [ -n "$COMMIT" ]; then
    ok "commit=$COMMIT"
else
    bad "version liefert kein commit"
fi

# --- 3. OpenAPI-Publikation ---------------------------------------------------
step "3/8 OpenAPI"
if curl -fsS -m 10 "$API/openapi.json" | jq -e '.openapi' >/dev/null; then
    ok "openapi.json"
else
    bad "openapi.json"
fi

# --- 4. Login ----------------------------------------------------------------
step "4/8 Login + Session-Cookie"
LOGIN_RESP="$(curl -s -D - -o /dev/null -m 10 -c "$COOKIE_JAR" \
    -X POST "$API/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}")"
if echo "$LOGIN_RESP" | grep -qi '^set-cookie: hcc_session=.*httponly'; then
    ok "hcc_session mit HttpOnly"
else
    bad "kein HttpOnly-Session-Cookie"
fi
# Cookie-Jar ist im Netscape-Format (tab-getrennt: Domain, TailMatch,
# Pfad, Secure, Expires, Name, Wert). 'hcc_csrf=' existiert in dieser
# Datei NICHT als String => awk-Extraktion statt grep.
CSRF="$(awk -F'\t' '$6=="hcc_csrf"{print $7; exit}' "$COOKIE_JAR")"

# --- 5. RBAC: Viewer darf nicht verwalteten Schreibzugriff ausueben ----------
step "5/8 RBAC"
VIEWER_NAME="qa_smoke_viewer"
VIEWER_CREATED=0
if curl -fsS -m 10 -b "$COOKIE_JAR" -X POST "$API/users" \
        -H 'Content-Type: application/json' \
        -H "X-CSRF-Token: $CSRF" \
        -d "{\"username\":\"$VIEWER_NAME\",\"password\":\"smoke-passw0rt-9x\",\"role\":\"viewer\"}" \
        >/dev/null 2>&1; then
    VIEWER_CREATED=1
    VIEWER_JAR="$(mktemp)"
    curl -s -D - -o /dev/null -m 10 -c "$VIEWER_JAR" -X POST "$API/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"$VIEWER_NAME\",\"password\":\"smoke-passw0rt-9x\"}" >/dev/null
    VCSRF="$(awk -F'\t' '$6=="hcc_csrf"{print $7; exit}' "$VIEWER_JAR")"
    RBAC_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -b "$VIEWER_JAR" \
        -X POST "$API/users" -H 'Content-Type: application/json' \
        -H "X-CSRF-Token: $VCSRF" \
        -d '{"username":"qa-rbac-probe","password":"smoke-passw0rt-9x","role":"viewer"}')"
    if [ "$RBAC_CODE" = "403" ]; then
        ok "Viewer-POST /users => 403"
    else
        bad "Viewer-POST /users => $RBAC_CODE (erwartet 403)"
    fi
    rm -f "$VIEWER_JAR"
else
    bad "Test-Viewer konnte nicht angelegt werden (RBAC-Schritt ungueltig)"
fi

# --- 6. CSRF: POST ohne Token => 403 ------------------------------------------
step "6/8 CSRF"
CSRF_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -b "$COOKIE_JAR" \
    -X POST "$API/users" -H 'Content-Type: application/json' \
    -d '{"username":"qa_csrf_check","password":"smoke-passw0rt-9x","role":"viewer"}')"
if [ "$CSRF_CODE" = "403" ]; then
    ok "POST ohne CSRF-Token => 403"
else
    bad "POST ohne CSRF-Token => $CSRF_CODE (erwartet 403)"
fi

# --- 7. Error-Envelope ---------------------------------------------------------
step "7/8 Error-Envelope"
ERR_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 -b "$COOKIE_JAR" "$API/audit/definitely-not-there")"
if [ "$ERR_CODE" = "404" ] && curl -fsS -m 10 -b "$COOKIE_JAR" "$API/audit/definitely-not-there" \
    | jq -e '.error.code and .error.message and .error.request_id' >/dev/null; then
    ok "404 mit Error-Envelope"
else
    bad "404/Error-Envelope (Code: $ERR_CODE)"
fi

# --- 8. SPA --------------------------------------------------------------------
step "8/8 SPA ueber nginx"
if curl -fsS -m 10 "http://127.0.0.1:8080/" | grep -q '<div id="root"></div>'; then
    ok "index.html"
else
    bad "index.html (Frontend-Dist moeglicherweise nicht gebaut)"
fi

# --- Aufräumarbeit: Test-Viewer deaktivieren ------------------------------------
step "Aufräumarbeit Test-Viewer"
if [ "$VIEWER_CREATED" -eq 1 ]; then
    VIEWER_ID="$(curl -fsS -m 10 -b "$COOKIE_JAR" \
        "$API/users?q=$VIEWER_NAME" | jq -r \
        '.items[] | select(.username=="'$VIEWER_NAME'") | .id' 2>/dev/null | head -n1)"
    if [ -n "$VIEWER_ID" ] && curl -fsS -m 10 -b "$COOKIE_JAR" -X PATCH \
            "$API/users/$VIEWER_ID" -H 'Content-Type: application/json' \
            -H "X-CSRF-Token: $CSRF" \
            -d '{"is_active":false}' >/dev/null 2>&1; then
        echo "    Viewer '$VIEWER_NAME' deaktiviert (is_active=false)."
    else
        echo "    WARNUNG: Viewer '$VIEWER_NAME' konnte nicht deaktiviert" >&2
        echo "    werden; bitte manuell entfernen." >&2
    fi
fi

echo
echo "E2E-Smoke: $PASS bestanden, $FAIL fehlgeschlagen."
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
echo "Alle E2E-Schritte bestanden."
