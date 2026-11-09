# Parallel-Entwicklung mit fünf OpenCode-Sessions

## Voraussetzungen

1. Repository initialisiert; **ein** Foundation-Agent hat R0 sowie Contracts angelegt und commitet.
2. `main` enthält den geprüften Foundation-Commit und alle Tests laufen.
3. Jeder Agent arbeitet in einem eigenen Git-Worktree und eigenen Branch.
4. Keine zwei Agents bearbeiten dieselben Dateien. Integrationsreview erfolgt nach den Feature-Merges.

## Besitzbereiche
| Agent | Eigentümer-Dateien (vorgesehene Verzeichnisnamen) | Kein Schreibzugriff |
| --- | --- | --- |
| 1 backend-auth | `backend/app/auth/**`, `backend/app/users/**`, `backend/tests/auth/**` | `backend/app/contracts/**`, `backend/alembic/**` ohne Abstimmung |
| 2 frontend | `frontend/src/pages/**`, `frontend/src/components/**`, `frontend/src/features/**`, `frontend/src/styles/**` | `frontend/src/api/generated/**`, Backend-Verträge |
| 3 proxmox | `backend/app/integrations/proxmox/**`, `backend/app/inventory/proxmox/**`, `backend/tests/proxmox/**` | allgemeine Contracts und Migrationen |
| 4 telemetry | `backend/app/integrations/monitoring/**`, `backend/app/integrations/pihole/**`, `backend/app/integrations/truenas/**`, `backend/app/integrations/tailscale/**`, `backend/app/integrations/docker/**`, `backend/tests/integrations/**` | Global-Konfiguration und Contracts |
| 5 qa-security | `tests/e2e/**`, `tests/security/**`, `scripts/qa/**`, `docs/quality/**` | Feature-Code; nur Issues/Vorschläge schreiben |

Diese Verzeichnisnamen sind Sollkonventionen: Foundation-Agent muss sie festlegen, bevor Folge-Agenten starten. Bei Abweichungen `docs/architecture.md` als endgültige Quelle verwenden.

## Abhängigkeitsregel
- Frontend implementiert zunächst gegen versionierte OpenAPI-Mocks/Fixtures, **niemals** gegen frei erfundene Endpoints.
- Proxmox benötigt Ressourcen-Schema/Adapter-Protokoll der Foundation.
- Monitoring wird als getrennte, abschaltbare Integration gebaut; fehlende Dienste dürfen HCC nicht blockieren.
- QA schreibt Harness und Contract-Tests parallel; E2E erst nach Integration.
- R2 Topologie erfolgt vorzugsweise nach R1 Proxmox oder parallel nur gegen eingefrorene Inventar-Contracts.

## Start (Linux, Bash)
```bash
mkdir -p ~/projects
cd ~/projects/homelab-control-center
git status --short
# Nur nach abgeschlossenem Foundation-Commit und sauberem main:
git switch main
for pair in 'auth auth' 'frontend frontend' 'proxmox proxmox' 'telemetry telemetry' 'qa qa'; do
  set -- $pair
  git worktree add "../hcc-$1" -b "feature/$2"
done
git worktree list
```

Im jeweiligen Terminal:
```bash
cd ~/projects/hcc-auth && opencode
# Weitere Terminals: hcc-frontend, hcc-proxmox, hcc-telemetry, hcc-qa
```

Prompt je Agent: `Lies AGENTS.md, MASTER_PROMPT.md, docs/PARALLEL_WORKFLOW.md und agent-tasks/0X-*.md. Bearbeite ausschließlich deinen Bereich; führe Tests aus und committe auf deinem Feature-Branch. Kein Merge.`

## Review und Merge
Pro Feature zunächst `git diff main...feature/<name>`, Commit-Historie, Testreport und Security-Risiken prüfen. Danach **sequenziell** in separatem Integrationszweig mergen, bei Konflikten stoppen, Tests erneut ausführen. QA-Agent führt nach allen Merges vollständige Contract-/E2E-/Security-Tests aus. Erst dann `main` aktualisieren. Keine automatischen Merge-Kommandos für den Agenten freigeben.

## Performance / GPU
Fünf Sessions bedeuten fünf unabhängige Request-Streams zum gleichen Modell. Mit 2 Sessions starten, dann 3 oder 5 anhand realer Werte (TTFT, Output-Tokens/s, Queue-Time, VRAM, Kontext-Cache und Fehlerrate) testen. LiteLLM-Rate-Limits und Inferenzserver-Concurrency beachten. Kein vorausgesetzter linearer Geschwindigkeitsgewinn.
