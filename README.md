# HCC 2.0 — OpenCode Starterpaket

Dateien:
- `MASTER_PROMPT.md`: projektspezifischer Masterauftrag, Scope und Releaseplan.
- `AGENTS.md`: permanente, automatisch geladene Projektregeln für OpenCode.
- `docs/DEPLOYMENT_PLAYBOOK.md`: LXC-/Tailscale-Vorbereitung, Sicherheit, Deployment-Vertrag, Abnahmetests.
- `docs/PARALLEL_WORKFLOW.md`: Worktrees, Rollen, Merge und GPU-Durchsatz.
- `agent-tasks/01-...05-...`: fünf einzeln ausführbare OpenCode-Aufträge.

**Wichtig:** Vor fünf parallelen Sessions erst Foundation in einer einzelnen Session implementieren und gemeinsame API-Verträge committen. Anschließend separate Worktrees pro Agent.

**Keine produktive Installation erfolgt durch diese Dateien.** Der initiale LXC-Anlegebefehl ist ein überprüfbares Beispiel mit expliziten Platzhaltern. Realen Proxmox-Zugriff und Schreibaktionen erst nach Freigabe.

## Status: R0 Foundation (Branch `foundation`)

- **Backend (FastAPI):** API-Grundgerüst unter `/api/v1` (Health, Version, Auth, Users, Integrations, Resources, Audit), RBAC, Server-Sessions, CSRF (Double-Submit), Rate-Limit, Audit, einheitliche Error-Envelope. **63 Tests grün** (in-memory SQLite), Lint (Ruff) clean.
- **Contracts:** `backend/app/contracts/` (frozen) + verbindlicher OpenAPI-Snapshot `backend/contracts/openapi.v1.json` (Snapshot-Test verhindert Drift). Details in `docs/api-contracts.md`.
- **Adapter-Interface:** `backend/app/adapters/` (Protokoll, Fehlerhierarchie, SecretsProvider) frozen; Registry in R0 bewusst leer → Verify antwortet ehrlich mit `501 not_implemented`.
- **DB:** Initialmigration `backend/alembic/versions/0001_initial.py` (upgrade/downgrade getestet, SQLite + PostgreSQL-DDL-konform).
- **Deployment-Gerüst:** `scripts/deploy-lxc.sh` (idempotent), `deploy/systemd/hcc-api.service`, `deploy/nginx/hcc.conf` — **noch nicht in echter Infrastruktur ausgeführt** (keine Freigabe erfolgt).
- **Frontend:** R0-Shell (Login + Dashboard gegen echte v1-Endpoints), Status `code_only` — Build/Typecheck/Tests auf der Entwicklungsmaschine **nicht ausführbar** (kein Node.js installiert). Siehe `docs/foundation-handoff.md`.
- **Doku:** `docs/architecture.md` (Verzeichnis-Konventionen, endgültige Quelle), `docs/api-contracts.md`, `docs/foundation-handoff.md`.

**Nächste Schritte:** Foundation-Branch reviewen und in `main` integrieren (Betreiber, kein Auto-Merge); danach parallele Agent-Sessions nach `docs/PARALLEL_WORKFLOW.md` starten.
