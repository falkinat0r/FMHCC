#!/usr/bin/env bash
#
# HCC QA-Pipeline (R1, Agent 5) — alle Gates in einem Aufruf.
#
# Aufruf (aus beliebigem Verzeichnis, Repository-Root wird auto-geleitet):
#   bash scripts/qa/run-qa.sh
#
# Gates:
#   1. Secret-Scan            (scripts/qa/scan_secrets.py)
#   2. Backend-Lint           (ruff check)
#   3. Backend-Unit-Tests     (pytest, backend/tests)
#   4. OpenAPI-Drift          (scripts/qa/check_openapi_drift.py — schreibfrei)
#   5. QA-Suite               (pytest, tests/ auf Repository-Root)
#   6. Frontend               (tsc, build, vitest, lint)
#   7. Dependency-Audits      (uv audit, npm audit — Netzwerk: FAILURE oder
#                              BLOCKED, nie stiller Green-Pass)
#   8. Deploy-Invarianten     (scripts/qa/check_deploy_artifacts.py)
#
# Exit-Code:
#   0 = alle Gates bestanden
#   1 = mindestens ein Gate FAILED
#   2 = alle Gates bestanden/fehlend, aber mindestens ein Gate BLOCKED
#       (keine belastbare Aussage, z. B. Netzwerkfehler beim Audit)

set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

FAILED_GATES=()
BLOCKED_GATES=()

say() { printf '%s\n' "$*"; }

run_gate() {
    local name="$1"
    local blocked_on_rc2="${2:-0}"
    shift 2
    say ""
    say "==> GATE: $name"
    "$@"
    local rc=$?
    if [ "$rc" -eq 0 ]; then
        say "    GATE OK: $name"
    elif [ "$rc" -eq 2 ] && [ "$blocked_on_rc2" -eq 1 ]; then
        say "    GATE BLOCKED (keine belastbare Aussage): $name"
        BLOCKED_GATES+=("$name")
    else
        say "    GATE FAILED: $name (exit $rc)"
        FAILED_GATES+=("$name")
    fi
}

# --- Gate 1: Secret-Scan -------------------------------------------------------
run_gate "Secret-Scan" 0 python3 scripts/qa/scan_secrets.py

# --- Gate 2: Backend-Lint ------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    run_gate "Backend-Lint (ruff)" 0 bash -c "cd backend && uv run ruff check ."
else
    say ""; say "==> GATE: Backend-Lint (ruff)"
    say "    GATE BLOCKED: uv nicht installiert"; BLOCKED_GATES+=("Backend-Lint (ruff)")
fi

# --- Gate 3: Backend-Unit-Tests ------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    run_gate "Backend-Unit-Tests (pytest)" 0 bash -c "cd backend && uv run pytest -q"
else
    say ""; say "==> GATE: Backend-Unit-Tests (pytest)"
    say "    GATE BLOCKED: uv nicht installiert"; BLOCKED_GATES+=("Backend-Unit-Tests (pytest)")
fi

# --- Gate 4: OpenAPI-Drift ------------------------------------------------------
if command -v uv >/dev/null 2>&1; then
    run_gate "OpenAPI-Drift (Contract-Snapshot)" 1 \
        bash -c "uv run --project backend python scripts/qa/check_openapi_drift.py"
else
    say ""; say "==> GATE: OpenAPI-Drift (Contract-Snapshot)"
    say "    GATE BLOCKED: uv nicht installiert"; BLOCKED_GATES+=("OpenAPI-Drift (Contract-Snapshot)")
fi

# --- Gate 5: QA-Suite (tests/ auf Root) -----------------------------------------
if command -v uv >/dev/null 2>&1; then
    run_gate "QA-Suite (pytest tests/)" 0 \
        bash -c "uv run --project backend python -m pytest tests -q"
else
    say ""; say "==> GATE: QA-Suite (pytest tests/)"
    say "    GATE BLOCKED: uv nicht installiert"; BLOCKED_GATES+=("QA-Suite (pytest tests/)")
fi

# --- Gate 6: Frontend (Node.js) --------------------------------------------------
if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    run_gate "Frontend-Typecheck (tsc)" 0 \
        bash -c "cd frontend && npx tsc -b --noEmit"
    run_gate "Frontend-Build (vite)" 0 \
        bash -c "cd frontend && npm run build >/dev/null"
    run_gate "Frontend-Tests (vitest)" 0 \
        bash -c "cd frontend && npx vitest run"
    run_gate "Frontend-Lint (eslint)" 0 \
        bash -c "cd frontend && npm run lint"
else
    say ""; say "==> GATE: Frontend (tsc/build/vitest/lint)"
    say "    GATE BLOCKED: node/npm nicht installiert"
    BLOCKED_GATES+=("Frontend (tsc/build/vitest/lint)")
fi

# --- Gate 7: Dependency-Audits (Netzwerk) -----------------------------------------
# Semantik: 0=clean, 1=vulnerable, 2=blocked. Ein Audit mit Netzwerkfehler
# darf KEIN Green-Pass sein => BLOCKED.
py_audit() {
    local out
    out="$(uv audit --project backend 2>&1)"
    local rc=$?
    say "$out"
    if [ "$rc" -eq 0 ]; then
        return 0
    fi
    if echo "$out" | grep -qiE "cve-|vulnerab"; then
        return 1
    fi
    say "    (Audit-Ausfuehrung fehlgeschlagen — als BLOCKED gewertet)"
    return 2
}
if command -v uv >/dev/null 2>&1; then
    run_gate "Dependency-Audit (Python, uv audit)" 1 py_audit
else
    say ""; say "==> GATE: Dependency-Audit (Python, uv audit)"
    say "    GATE BLOCKED: uv nicht installiert"; BLOCKED_GATES+=("Dependency-Audit (Python, uv audit)")
fi
if command -v npm >/dev/null 2>&1; then
    run_gate "Dependency-Audit (npm, prod-Abhaengigkeiten)" 1 \
        bash -c "cd frontend && npm audit --omit=dev"
else
    say ""; say "==> GATE: Dependency-Audit (npm, prod-Abhaengigkeiten)"
    say "    GATE BLOCKED: npm nicht installiert"; BLOCKED_GATES+=("Dependency-Audit (npm, prod-Abhaengigkeiten)")
fi

# --- Gate 8: Deploy-Invarianten --------------------------------------------------
run_gate "Deploy-Invarianten (systemd/nginx/deploy-lxc.sh)" 1 \
    python3 scripts/qa/check_deploy_artifacts.py

# --- Fazit --------------------------------------------------------------------------
say ""
say "================================================================"
if [ "${#FAILED_GATES[@]}" -gt 0 ]; then
    say "Fazit: FAILED — ${#FAILED_GATES[@]} Gate(s) bestanden nicht:"
    for g in "${FAILED_GATES[@]}"; do say "  - $g"; done
    say "Exit 1"
    exit 1
fi
if [ "${#BLOCKED_GATES[@]}" -gt 0 ]; then
    say "Fazit: GREEN-MIT-RESERVE — ${#BLOCKED_GATES[@]} Gate(s) BLOCKED:"
    for g in "${BLOCKED_GATES[@]}"; do say "  - $g"; done
    say "Exit 2"
    exit 2
fi
say "Fazit: ALLE GATES BESTANDEN. Exit 0"
exit 0
