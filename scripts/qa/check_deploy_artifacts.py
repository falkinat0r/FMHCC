"""Statische Deploy-Invarianten (HCC QA, Agent 5).

Prueft die Deployment-Artefakte auf verbindliche Invarianten aus
docs/DEPLOYMENT_PLAYBOOK.md und der R1-Deploy-Review, OHNE ein System
anzutasten (funktioniert in CI, wo kein LXC erreichbar ist).

Geprueft:
- deploy/systemd/hcc-api.service  (User/Group, Loopback, Hardening,
  Alembic vor Start, Health-Probe, Start-Timeout)
- deploy/nginx/hcc.conf           (nur 127.0.0.1, Proxyziel, Header,
  server_tokens, SPA-Root)
- scripts/deploy-lxc.sh           (set -euo pipefail, root-Check,
  Preflight, --list, --rollback, keine curl|bash, Datei-Rechte,
  Zufalls-Bootstrap-Token)

Exit-Code: 0 = alle Invarianten gehalten, 1 = Verstoess,
2 = Pruefung nicht moeglich (Datei fehlt).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SERVICE = ROOT / "deploy" / "systemd" / "hcc-api.service"
NGINX = ROOT / "deploy" / "nginx" / "hcc.conf"
DEPLOY_SH = ROOT / "scripts" / "deploy-lxc.sh"


def _read(path: Path) -> str | None:
    if not path.is_file():
        print(f"FEHLER: Datei fehlt: {path.relative_to(ROOT)}")
        return None
    return path.read_text(encoding="utf-8")


def _joined_lines(text: str) -> str:
    """Systemd-Zeilenumbruch (Backslash am Zeilenende) auflösen, damit
    Multi-Line-Commande (z. B. ExecStart mit Fortsetzung) gecheckt werden
    können."""
    return re.sub(r"\\\n\s*", " ", text)


def check_service(text: str) -> list[str]:
    text = _joined_lines(text)
    errors: list[str] = []

    def need(pattern: str, label: str) -> None:
        if not re.search(pattern, text, re.MULTILINE):
            errors.append(f"hcc-api.service: fehlt/verletzt: {label}")

    # Unprivilegierte Serviceidentitaet
    need(r"^User=hcc\s*$", "User=hcc")
    need(r"^Group=hcc\s*$", "Group=hcc")
    # Loopback-Zwang: nur 127.0.0.1:8000
    if not re.search(r"^ExecStart=.*--host 127\.0\.0\.1 --port 8000", text, re.MULTILINE):
        errors.append("hcc-api.service: ExecStart muss nur 127.0.0.1:8000 binden")
    if re.search(r"^ExecStart=.*--host\s+(?!127\.0\.0\.1)", text, re.MULTILINE):
        errors.append("hcc-api.service: ExecStart bindet an ein Nicht-Loopback-Interface")
    # Migration vor dem Start
    need(r"^ExecStartPre=.*alembic upgrade head", "ExecStartPre mit 'alembic upgrade head'")
    # R1: Health-Probe nach dem Start + ausreichend Start-Timeout
    need(r"^ExecStartPost=", "ExecStartPost (Health-Probe nach Start)")
    m = re.search(r"^TimeoutStartSec=(\d+)", text, re.MULTILINE)
    if not m or int(m.group(1)) < 60:
        errors.append("hcc-api.service: TimeoutStartSec fehlt oder < 60")
    # Hardening
    for key, label in (
        (r"^NoNewPrivileges=yes", "NoNewPrivileges=yes"),
        (r"^PrivateTmp=yes", "PrivateTmp=yes"),
        (r"^ProtectSystem=full", "ProtectSystem=full"),
        (r"^ProtectHome=yes", "ProtectHome=yes"),
        (r"^Restart=on-failure", "Restart=on-failure"),
    ):
        need(key, label)
    # Environment
    need(r"^EnvironmentFile=/etc/hcc/hcc\.env", "EnvironmentFile=/etc/hcc/hcc.env")
    # Niemand darf den Docker-Socket erreichen
    if "docker.sock" in text or "DockerSocket" in text:
        errors.append("hcc-api.service: Bezug auf Docker-Socket gefunden")
    return errors


def check_nginx(text: str) -> list[str]:
    errors: list[str] = []

    def need(pattern: str, label: str) -> None:
        if not re.search(pattern, text, re.MULTILINE):
            errors.append(f"hcc.conf: fehlt/verletzt: {label}")

    # Nur Loopback-Listenports; kein externes `listen 80;`/`listen 443;`
    listens = re.findall(r"^\s*listen\s+([^;\s]+);", text, re.MULTILINE)
    if not listens:
        errors.append("hcc.conf: keine listen-Direktive gefunden")
    for addr in listens:
        if not (addr.startswith("127.0.0.1:") or addr.startswith("[::1]")):
            errors.append(f"hcc.conf: listen auf Nicht-Loopback-Adresse: {addr}")
    # Proxy auf Loopback-Backend
    need(r"proxy_pass\s+http://hcc_api;", "proxy_pass an hcc_api-Upstream")
    if not re.search(r"server\s+127\.0\.0\.1:8000\s*;", text, re.MULTILINE):
        errors.append("hcc.conf: Upstream muss 127.0.0.1:8000 adressieren")
    # Sicherheits-Header + Server-Anonymisierung
    need(r"server_tokens off;", "server_tokens off")
    need(r"add_header X-Content-Type-Options nosniff", "Header X-Content-Type-Options")
    need(r"add_header X-Frame-Options DENY", "Header X-Frame-Options")
    need(r"add_header Referrer-Policy no-referrer", "Header Referrer-Policy")
    # SPA-Root
    need(r"root /opt/hcc/current/frontend/dist;", "root /opt/hcc/current/frontend/dist")
    return errors


def check_deploy_script(text: str) -> list[str]:
    errors: list[str] = []

    def need(pattern: str, label: str) -> None:
        if not re.search(pattern, text, re.MULTILINE):
            errors.append(f"deploy-lxc.sh: fehlt/verletzt: {label}")

    need(r"set -euo pipefail", "set -euo pipefail")
    need(r'\[ "\$\(id -u\)" -ne 0 \]', "root-Check")
    need(r"/etc/debian_version", "Debian-Check")
    # R1: Preflight, Release-Liste, Rollback
    need(r"preflight", "Preflight-Pruefung (Stufe 0)")
    need(r"--list", "Subbefehl --list (Release-Liste)")
    need(r"--rollback", "Subbefehl --rollback <sha>")
    # Keine unsicheren Remote-Shell-Muster — nur echte Befehlszeilen
    # (Kommentare, log-/echo-Zeilen duerfen das Wort enthalten).
    command_lines = [
        ln
        for ln in text.splitlines()
        if ln.strip()
        and not ln.strip().startswith("#")
        and not re.match(r"\s*(log|echo|printf)\b", ln)
    ]
    joined_commands = "\n".join(command_lines)
    if re.search(r"curl[^|&]*\|\s*(ba)?sh\b", joined_commands):
        errors.append("deploy-lxc.sh: 'curl ... | sh' Muster gefunden")
    if re.search(r"wget[^|&]*\|\s*(ba)?sh\b", joined_commands):
        errors.append("deploy-lxc.sh: 'wget ... | sh' Muster gefunden")
    # Idempotente Service-Identitaet
    need(r"if ! id -u hcc", "idempotente User-Anlage (if ! id -u hcc)")
    # Datei-Rechte
    need(r"chmod 640", "chmod 640 fuer hcc.env")
    need(r"chown root:hcc", "chown root:hcc fuer hcc.env")
    need(r"chmod 600", "chmod 600 fuer .pg_password")
    # Bootstrap-Token: Zufall, kein hartkodiertes Literal
    if not re.search(r"openssl rand -hex 24", text):
        errors.append("deploy-lxc.sh: Bootstrap-Token muss per 'openssl rand -hex 24' entstehen")
    if re.search(r"HCC_BOOTSTRAP_TOKEN=[A-Za-z0-9]{16,}", text):
        errors.append("deploy-lxc.sh: hartkodertes Bootstrap-Token-Literal gefunden")
    # Alembic-Migration laeuft nicht parallel zum App-Start (Unit regelt es)
    if re.search(r"^alembic ", text, re.MULTILINE):
        errors.append("deploy-lxc.sh: Migration muss ueber systemd ExecStartPre laufen")
    return errors


def main() -> int:
    errors: list[str] = []
    service = _read(SERVICE)
    nginx = _read(NGINX)
    deploy_sh = _read(DEPLOY_SH)
    if service is None or nginx is None or deploy_sh is None:
        print("\nFEHLER: Pruefung nicht moeglich (Dateien fehlen).")
        return 2

    errors += check_service(service)
    errors += check_nginx(nginx)
    errors += check_deploy_script(deploy_sh)

    if not errors:
        print("OK: alle Deploy-Invarianten gehalten (systemd, nginx, deploy-lxc.sh).")
        return 0

    print(f"\n{len(errors)} Invarianten-Verstoess:")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
