# Vorschlag: Alembic-Offline-Modus in `backend/alembic/env.py` reparieren (Agent 1, R1)

- **Status:** offen (geteilter Bereich `backend/alembic/**` — keine Änderung ohne Abstimmung)
- **Autor:** Agent 1 (backend-auth), Branch `feature/auth`
- **Betroffener Bereich:** `backend/alembic/env.py` (Shared, geteilter Bereich gemäß `docs/PARALLEL_WORKFLOW.md`)
- **Verletzte Regel:** keine — dieser Vorschlag existiert, weil die Reparatur in einem Bereich liegt, in dem Agent 1 keinen Schreibzugriff hat (AGENTS.md §1/§4)

## 1. Befund (echter R0-Defekt)

`backend/alembic/env.py::run_migrations_offline()` übergibt das gesamte
`[alembic]`-INi-Sektion-Dict per `**` an `context.configure()`:

```python
def run_migrations_offline() -> None:
    """Offline-Modus: SQL-Script ohne live Verbindung."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    context.configure(
        **configuration,          # <-- script_location, file_template, sqlalchemy.url, ...
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
```

`context.configure()` erwartet die Datenbank-URL als **Positional/Named
Parameter `url=...`**, nicht als ini-Key `sqlalchemy.url`. Der ini-Key
landet in `**kwargs` und wird vom `MigrationContext` ignoriert. Ergebnis:
Der Offline-Modus kann **keine Migration rendern** und wirft:

```
Exception: Connection, url, or dialect_name is required.
```

Reproduziert (Probe gegen die echte `0001_initial.py`, ohne Live-Server):

```
alembic upgrade head --sql   # => Exception: Connection, url, or dialect_name is required.
```

Der **Online-Modus** ist davon nicht betroffen (`engine_from_config` mit
`prefix="sqlalchemy."` liest `sqlalchemy.url` korrekt) — R0 wurde nur
online getestet, daher wurde der Defekt nicht sichtbar.

## 2. Warum Agent 1 das in R1 nicht repariert hat

- `backend/alembic/**` ist gemäß `docs/PARALLEL_WORKFLOW.md` ein
  **geteilter Bereich** („ohne Abstimmung" kein Schreibzugriff für Agent 1).
- `AGENTS.md` §4: Änderungen an gemeinsamen Contracts/Migrationen nur über
  dokumentierte Vorschläge, nicht stillschweigend.
- Das R1-Goal „PostgreSQL-Verifikation" wurde daher mit einer **Test-Env**
  umgesetzt, die die **echten** R0-`versions/`-Skripte unverändert gegen das
  PostgreSQL-Dialekt rendert (siehe `backend/tests/test_postgresql.py`).

## 3. Vorgeschlagene Reparatur (minimal, ohne Verhaltenänderung für Online)

Nur `run_migrations_offline()` anpassen — `url` explizit als Parameter
übergeben (Standard-Muster aus der Alembic-Doku, dynamisch via `get_url()`):

```python
def run_migrations_offline() -> None:
    """Offline-Modus: SQL-Script ohne live Verbindung."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
```

- `run_migrations_online()` bleibt unverändert.
- Keine Änderung an `versions/0001_initial.py` oder `alembic.ini`.
- Keine Änderung am Datenmodell, am `script_location` oder an der
  `prepend_sys_path`-Konfiguration.

## 4. Test, der die Reparatur absichert (bereits in R1 vorhanden)

`backend/tests/test_postgresql.py` rendert die Initialmigration offline
gegen das PostgreSQL-Dialekt und prüft:

- alle 7 Tabellen (`CREATE TABLE users|user_sessions|integrations|resources|resource_relations|action_jobs|audit_events`)
- alle benannten CHECK-Constraints (`ck_users_role`, `ck_integrations_adapter`, …)
- Foreign Keys mit `ON DELETE CASCADE` / `ON DELETE SET NULL`
- `UUID`-Typ im DDL

Der Test nutzt aktuell eine tmp-`env.py` (Wechselarbeit), die die echten
`versions/`-Skripte ausführt. **Nach Freigabe und Reparatur** kann der Test
die echte `backend/alembic/env.py` nutzen (tmp-Env entfernen) — dann ist der
Test ein direkter Regression-Test auf den behobenen Defekt.

## 5. Auswirkungen der Freigabe

- Keine Schema-/Datenänderung, nur der Offline-Rendering-Pfad wird lauffähig.
- Enables `alembic upgrade head --sql` für DDL-Review ohne Live-DB (z. B. in
  CI oder im Deployment-Playbook).
- Online-Migrations-Workflow bleibt identisch.

## 6. Entscheidung

- [ ] Freigabe: Reparatur in `backend/alembic/env.py` (Agent 1 oder
      Koordinierung führt sie durch und aktualisiert `test_postgresql.py`)
- [ ] Ablehnung: Defekt bleibt, R1-Test bleibt auf tmp-Env-Basis

Empfehlung: **Freigabe** — der Offline-Modus ist ein dokumentiertes
Alembic-Feature, das in R0 versehentlich defekt ist; die Reparatur ist
minimal und ohne Nebeneffekte.

Freigabe durch: Koordinierung / Integrationsreview (geteilter Bereich).
