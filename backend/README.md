# HCC Backend — API (R0 Foundation)

FastAPI-Backend des Homelab Control Centers. R0 liefert das Fundament:
eingefrorene API-Contracts, Auth (Bootstrap/Login/Session/CSRF/RBAC),
Audit, Adapter-Interface, Inventar-Dedup, Alembic-Migration und Tests.

## Entwicklung

Voraussetzung: [`uv`](https://docs.astral.sh/uv/) (>= 0.5).

```bash
uv sync --extra dev            # Venv + Abhaengigkeiten
uv run uvicorn app.main:app --factory --port 8000   # App-Start (bindet 127.0.0.1)
uv run pytest                  # komplette Test-Suite (in-memory SQLite)
uv run ruff check .            # Lint
```

Konfiguration läuft über Environment-Variablen mit Präfix `HCC_`
(siehe `../.env.example`). Secrets gehören nicht ins Repository, sondern
nach `/etc/hcc/secrets.env` (Produktion).

## API-Contracts

Der OpenAPI-Snapshot in [`contracts/openapi.v1.json`](contracts/openapi.v1.json)
ist der **verbindliche Contract**. Er wird generiert über:

```bash
uv run python ../scripts/generate-openapi.py
```

Regel: Jede (beabsichtigte) Contract-Änderung erfordert
1. Änderung der Pydantic-Contracts in `app/contracts/`,
2. Regenerierung des Snapshots,
3. Review des Diffs,
4. Eintrag in `../docs/api-contracts.md`.

Der Test `tests/test_contracts_snapshot.py` stellt sicher, dass der
committete Snapshot und die App-Definition identisch sind.

## Datenbank / Migrationen

Production: PostgreSQL. Tests: in-memory SQLite (Migration läuft in
`tests/test_migration.py` gegen eine echte SQLite-Datei durch:
upgrade + downgrade + Revisions-Prüfung).

```bash
uv run alembic upgrade head     # gegen HCC_DATABASE_URL
uv run alembic revision --autogenerate -m "..."   # nur nach Modell-Änderung
```

Die Initialmigration `alembic/versions/0001_initial.py` ist R0-frozen.
Constraint-Namen folgen `app/db/base.py` (NAMING_CONVENTION) und sind
deterministisch.

## Struktur

```
app/
  api/v1/        Endpoints (/api/v1/...)
  contracts/     EINGEFRORENE Pydantic-Contracts (frozen, R0)
  auth/          Bootstrap, Sessions, CSRF, RBAC, Rate-Limit, Hashing
  audit/         Audit-Service (append-only)
  adapters/      Adapter-Protokoll, Fehlerhierarchie, SecretsProvider (frozen)
  integrations/  Adapter-Registry (R0: bewusst leer)
  inventory/     Dedup/Normalisierung (upsert_resources)
  models/        ORM-Modelle (Schema R0-frozen)
  db/            Engine, Session-Factory, Base (Naming-Convention)
tests/           pytest-Suite (isoliert, in-memory SQLite)
contracts/       openapi.v1.json (verbindlicher Contract-Snapshot)
```

## Scope-Hinweis R0

- Keine echte Infrastruktur-Anbindung (Adapter-Registry leer, Endpunkte
  antworten ehrlich mit `not_implemented`).
- Keine KI-Funktionen (ausdrücklich aus Scope, siehe MASTER_PROMPT.md).
- Deployment-Gerüst: `../deploy/` und `../scripts/deploy-lxc.sh`
  (siehe `../docs/DEPLOYMENT_PLAYBOOK.md`).
