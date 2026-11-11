#!/usr/bin/env python3
"""Secret-Scanner (HCC QA, Agent 5).

Prueft das Repository auf versehentlich eingebundene Secrets, Token und
Verbindungszugraenge. Reine Standardbibliothek (keine Netzwerk-/
Paketabhaengigkeit), damit er in CI und im LXC lauffaehig ist.

Regeln (bewusst konservativ, Falsch-Positiv-Freigabe nur dokumentiert):
- Cloud-/Platform-Keys (AWS, GitHub, Slack, OpenAI)
- Private-Key-Blöcke
- Datenbank-URLs mit Benutzer/Passwort (außer dokumentierte Beispielsysteme)
- Langhex-Tokens (32+ Zeichen, z. B. token_hex)
- Nicht-leere Bootstrap-/Passwort-Zuweisungen ausserhalb von .env.example

Exit-Code: 0 = sauber, 1 = Befunde, 2 = Pruefung nicht moeglich.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Bewusst freigegebene Test-Platzhalter (docs/foundation-handoff.md §5:
# "Test-Daten sind klar markierte Placeholders").
ALLOWLIST = {
    "test-bootstrap-token-0123456789abcdef",
    "qa-bootstrap-token-0123456789abcdef",
    "bootstrap-pass-123",
    "viewer-pass-123",
    "qa-admin-pass-1234",
    "qa-viewer-pass-1234",
    "qa-operator-pass-1234",
    "falsch-passw0rt",
    "lange-passw0rt-123",
    "irgend-32-stellige-t0ken",
    "passw0rt-12345",
    "deact-pass-12345",
    "viewer-pass-12345",
    "fuzz-pass-12345",
    "geheim-passw0rt-xyz",
    "short-pw-xyz",
    "top-secret-value-0123456789abcdef",  # nur als Suchmuster in Tests
    "sehr-geheimes-passwort-123",
    "abc123",
    # --- R1-Integration (2026-11-11, integrated Tree): dokumentierte
    # Falsch-Positiv-Freigaben (Integration-Report, Abschnitt "Secret-Scan").
    # Keine der Werte ist ein echtes Secret:
    "deactivate-pass-123",  # tests/auth/test_auth_hardening.py — Test-User 'deactivate-me' (feature/auth)
    "alt-passwort-123",  # tests/auth/test_password_change.py — Test-Literal (feature/auth)
    "0123456789abcdef01234789abcdef012345",  # PVEAPIToken-Testfixtur: tests/proxmox/conftest.py, test_config.py, fixtures/server.py — deterministische Parse-Tests gegen lokalen Mock-Server
    "ffffffffffffffffffffffffffffffff",  # Fake-Secret fuer Leakage-/Parse-Tests: tests/proxmox/test_client.py, test_adapter.py
    "00000000000000000000000000000000",  # 'bewusst falscher Token' fuer Negativ-Test: tests/proxmox/test_discovery.py
    "ProxmoxToken",  # Typ-Annotation app/integrations/proxmox/client.py — kein Literal
    "_split_token",  # Tuple-Unpacking app/integrations/proxmox/config.py — kein Literal
    "user:pass@",  # Docstring-Beispiel app/integrations/monitoring/httputil.py — keine echte URL
}

RULES: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "AWS key",
        "AWS Access Key ID",
        re.compile(r"(?:A3T[A-Z0-9]|AKIA|ASIA)[A-Z0-9]{16}"),
    ),
    (
        "GitHub token",
        "GitHub Personal Access Token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b"),
    ),
    (
        "Slack token",
        "Slack-Token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    ),
    (
        "OpenAI key",
        "OpenAI-Schlüssel",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    ),
    (
        "Private key",
        "Private Key-Block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    (
        "DB URL with credentials",
        "Datenbank-URL mit eingebettetem Passwort",
        re.compile(r"\b[a-z][a-z0-9+]*://[^/\s:@]+:[^/\s@]+@"),
    ),
    (
        "Long hex token",
        "Langes Hex-Token (mögliches Session-/API-Secret)",
        re.compile(r"\b[0-9a-f]{32,}\b"),
    ),
    (
        "Bootstrap token set",
        "Nicht-leeres HCC_BOOTSTRAP_TOKEN",
        re.compile(r"^HCC_BOOTSTRAP_TOKEN=([^\s]+)$", re.MULTILINE),
    ),
    (
        # Negative Lookahead: keine Code-Identifier/Funktionsaufrufe
        # (z. B. ``token = request_id_var.set(...)``), nur Literale.
        "Password assignment",
        "Passwort-Zuweisung mit Literal",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token)\s*[=:]\s*[\"']?"
            r"([A-Za-z0-9/+=!@#$%^&*_-]{12,})[\"']?"
            r"(?![A-Za-z0-9_.])"
        ),
    ),
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "tools",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
}
SKIP_FILES = {"uv.lock", "package-lock.json", "openapi.v1.json"}


@dataclass
class Finding:
    rule: str
    description: str
    path: str
    line: int
    preview: str


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name in SKIP_FILES:
            continue
        # Binaries/Artefakte: an Hand der ersten Bytes filtern
        try:
            head = path.open("rb").read(4096)
        except OSError:
            continue
        if b"\x00" in head:
            continue
        yield path, head


def scan() -> list[Finding]:
    findings: list[Finding] = []
    for path, _head in _iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for rule, description, pattern in RULES:
            for match in pattern.finditer(text):
                snippet = match.group(0)
                # Allowlist: klare Test-Platzhalter
                if any(allowed in snippet or snippet in allowed for allowed in ALLOWLIST):
                    continue
                if rule == "DB URL with credentials":
                    line_no = _line_of(text, match.start())
                    line_text = text.splitlines()[line_no - 1]
                    # Dokumentierte Dev-Default (backend/app/config.py, .env.example):
                    # User/Passwort "hcc" auf 127.0.0.1 ist ein Platzhalter, kein Secret.
                    if "hcc:hcc@127.0.0.1" in line_text:
                        continue
                    # Shell-Skripte referenzieren das Passwort via Umgebungsvariable
                    # (z. B. sed '...hcc:'"${PG_PASS}"'@...') — kein Literal.
                    if "${" in line_text or re.search(r"\$\{?[A-Za-z_]+\}?", snippet):
                        continue
                if rule == "Bootstrap token set":
                    value = match.group(1)
                    if not value or value in ALLOWLIST:
                        continue
                if rule == "Long hex token" and path.name.endswith((".py", ".ts")):
                    # SHA-256-Testkonstanten in Tests sind erlaubt
                    if "sha256" in text.lower() and "hexdigest" in text.lower():
                        continue
                # Kontextzeile (gekürzt, keine vollständigen Werte)
                line_no = _line_of(text, match.start())
                lines = text.splitlines()
                preview = lines[line_no - 1].strip()[:120] if line_no - 1 < len(lines) else ""
                if any(allowed in preview for allowed in ALLOWLIST):
                    continue
                findings.append(Finding(rule, description, str(path.relative_to(ROOT)), line_no, preview))
    return findings


def main() -> int:
    print(f"Secret-Scanner: {ROOT}")
    try:
        findings = scan()
    except Exception as exc:  # noqa: BLE001
        print(f"FEHLER: Pruefung nicht durchfuehrbar: {exc}")
        return 2

    if not findings:
        print("OK: keine Befunde.")
        return 0

    print(f"\n{len(findings)} Befund(e):")
    for f in findings:
        print(f"  [{f.rule}] {f.path}:{f.line} — {f.description}")
        print(f"      {f.preview}")
    print("\nHinweis: Bei Falsch-positiv: Freigabe in der ALLOWLIST mit Begründung dokumentieren.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
