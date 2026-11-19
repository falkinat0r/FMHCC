# R1 — Rollback (Proxmox-LXC)

**Stand:** 2026-11-19 · **Branch:** `deployment/r1-validation` (Basis: `master` = `9bf6afb`)
**Referenz:** `docs/deployment/R1-lxc-deployment.md` §14 (Kurzfassung)

Rollback- Ebenen, von minimal bis maximal:

| Ebene | Werkzeug | Deckt ab | RTO (Planwert) |
| --- | --- | --- | --- |
| L1 — Anwendung | `deploy-lxc.sh --rollback <sha>` | App-Code (Backend+Frontend-Release) | ~1–2 min (Restart + Probe) |
| L2 — Konfiguration | manuelle Datei-Restore (`hcc.env`, nginx, Unit) + Neustart | Konfigurationsfehler | ~5–10 min |
| L3 — Datenbank | `pg_restore` aus konsistentem Dump (s. Playbook §8) | Daten-Korruption / schlechte Migration | ~10–30 min (je nach Größe) |
| L4 — Ganzer LXC | PVE-CT-Backup-Restore | defektes Rootfs, irreparabler Zustand | ~15–60 min (je nach CT-Größe/Storage) |

**Wichtig:** L1 deckt **keine Daten** ab. Neue User/Integrations-/Audit-Rows
überleben einen App-Rollback. In R1 ist das unkritisch, weil es **keinen
Schema-Drift** gibt (exakt eine Migration `0001_initial` im Deployment-Stand);
wenn ein Rollback über ein Release mit neuer Migration zurückrollt, s. §4.

---

## 1. Rollback-Trigger (wann welche Ebene)

| Symptom | Ebene |
| --- | --- |
| Regressionsfehler nach Update, API antwortet (500er/Funktionsfehler) | L1 |
| Falsche `hcc.env`-/nginx-/Unit-Konfiguration (z. B. Tippfehler beim manuellen Edit) | L2 |
| Datenkorruption, fehlerhafte Migration, ungewollte Datenänderung | L3 |
| Defektes Rootfs, kaputte Pakete, fehlgeschlagene OS-Updates, Sicherheitsvorfall im LXC | L4 |
| Falscher Commit deployed (falscher Branch/Tag) | L1 (auf den korrekten, bereits deployten Release-Sha) |

## 2. L1 — Anwendungsebene (Standardfall)

**Voraussetzung:** das Ziel-Release wurde schon einmal deployed
(`git archive HEAD` unter `/opt/hcc/releases/<sha>`) — bei neuem
Deployment ohne Historie ist L1 **nicht** möglich → L4 (Backup aus
vor-Deployment-Zeitpunkt, Playbook §8).

```bash
# 1) Releases prüfen
sudo scripts/deploy-lxc.sh --list

# 2) Rollback auf den letzten bekannten guten Commit
sudo scripts/deploy-lxc.sh --rollback <guter-commit-sha>
```

Das Skript verifiziert die Existenz des Ziel-Verzeichnisses, setzt das
`current`-Symlink **atomar** (tmp + `mv`), führt `systemctl restart
hcc-api.service` aus und läuft die Health-Probe (bis 30 s auf
`health/live`-200).

**Verifikation nach L1:**

```bash
systemctl --no-pager status hcc-api.service --lines=10
curl -fsS http://127.0.0.1:8080/api/v1/health/live
curl -fsS http://127.0.0.1:8080/api/v1/version    # commit muss = <guter-commit-sha>
# Smoke bei Bedarf (Abnahmekriterien s. R1-acceptance-checklist.md):
sudo bash tests/e2e/e2e-smoke.sh
```

**Bekannte Ecken:**
- Die Migration läuft beim Neustart erneut als `ExecStartPre`
  (`alembic upgrade head`). Rollt das Ziel-Release **älter** als die
  aktuelle Schema-Version, schlägt die Migration fehl bzw. bleibt die
  DB auf dem neueren Stand — s. §4 (Schema-Drift).
- `/etc/hcc/hcc.env` bleibt unverändert (bewusst: persistent über
  Releases hinweg, enthält PG-Passwort + Bootstrap-Token). Wenn sich
  die Env-Keys zwischen Releases ändern, ist L2 zusätzlich nötig.
- Frontend-/Backend-Drift vermeiden: `current` zeigt immer auf einen
  kompletten Release-Ordner (Backend + Frontend zusammen).

## 3. L2 — Konfigurationsebene

```bash
# Belegte Stand: /etc/hcc/hcc.env (0640), /etc/hcc/.pg_password (0600),
# /etc/nginx/sites-available/hcc.conf, /etc/systemd/system/hcc-api.service
# 1) Sicherungskopie der aktuellen (defekten) Konfiguration
cp /etc/hcc/hcc.env /etc/hcc/hcc.env.defekt.$(date +%s)
cp /etc/nginx/sites-available/hcc.conf /root/hcc.conf.defekt.$(date +%s)

# 2) Bekannte gute Version wiederherstellen (aus L3-/L4-Sicherung oder
#    erneutem Generieren: deploy-lxc.sh generiert hcc.env nur, wenn sie
#    fehlt — für L2 also: Datei manuell auf den guten Stand setzen)

# 3) Anwenden
systemctl daemon-reload
nginx -t && systemctl reload nginx
systemctl restart hcc-api.service
```

**Nachweis:** `hcc-api.service` aktiv, `health/live` 200, Smoke bei Bedarf.

## 4. Schema-Drift (Migrationen) — R1-Bewertung

**R1-Fakt:** Der Deployment-Stand enthält genau **eine** Migration
(`0001_initial`). Es gibt in R1 **keinen** Schema-Drift zwischen Releases:
L1-Rollback ist ohne DB-Aktion sicher.

**Für R2+ (Regel, jetzt dokumentieren):** Wenn ein zukünftiges Release
eine neue Migration einführt, ist ein L1-Rollback auf ein Release **davor**
nur sicher, wenn die Migration abwärtskompatibel ist (additive Spalten)
oder über einen `alembic downgrade` planbar ist. Standard: additive
Migrations bevorzugen; destruktive Änderungen erfordern ein
vorab-getestetes L3-Dump + L1-Rollback-Kombi.

**Bewusster R1-Umfang (Validierungsfund V-9):** `alembic upgrade head` auf
**SQLite** erzeugt `audit_events.id` als `BIGINT` (kein rowid-Alias) →
Audit-Inserts schlagen dort fehl (empirisch in der R1-Validierung
nachgewiesen). Auf **PostgreSQL** lautet das DDL `id BIGSERIAL NOT NULL`
(Sequence → korrekt, per DDL-Rendering gegen den PostgreSQL-Dialekt
bewiesen). Das betrifft **nicht** den Produktivpfad (PG) und nicht
L1-Rollback (keine Schema-Änderung in R1); R2-Kandidat: Dialekt-
kompatible Integer-Bearbeitung der Migration.

## 5. L3 — Datenbankschwelle

```bash
# 1) Service anhalten (keine parallelen Writes)
systemctl stop hcc-api.service

# 2) Dump laden (Beispiel: konsistenter -Fc-Dump aus Playbook §8)
su - postgres -c "dropdb hcc"
su - postgres -c "createdb --owner=hcc hcc"
su - postgres -c "pg_restore -d hcc /var/backups/hcc-<datum>.dump"

# 3) Migration sicherstellen (Release-Stand!) und neu starten
systemctl start hcc-api.service        # ExecStartPre: alembic upgrade head
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
```

**Achtung:** `hcc.env`-Wert `HCC_DATABASE_URL` muss zum Ziel-DB-Stand
passen. L3 verliert alle Daten nach dem Dump-Zeitpunkt (RPO = Abstand
Dump → Vorfall). Regelmäßige Dumps sind Betriebspflicht (Playbook §8;
Automatisierung = R2-Kandidat D-I2).

## 6. L4 — Ganzer LXC (Letztes Mittel)

**Auf dem Proxmox-Host** (nur nach Freigabe, s. Playbook §3):

```bash
# Verfügbare CT-Backups
pvesh get /backup
pvesm status

# Neuen CT aus Backup anlegen (oder bestehend neu aufsetzen):
pct restore <CTID> <backupfile> --storage <storage>
# alternativ: CT neu anlegen (Playbook §5) + pg_restore (L3) + hcc.env (L2)

pct start <CTID>
```

**Verifikation:** Playbook §13 vollständig (Healthchecks, Smoke,
Tailscale-Erreichbarkeit).

## 7. Rollback-Verbote & Grenzen

- **Kein** Rollback über `git reset --hard`/`push --force` auf dem LXC-
  Checkout — Releases sind immutable (`git archive HEAD`-Snapshots).
- **Kein** manuelles Ändern der DB-Schema-Version (alembic_version-
  Tabelle) außer in begründeten, dokumentierten Fällen.
- **Secrets-Rollback:** `hcc.env`/`.pg_password` sind **nicht** Teil von
  L1; ihr Stand ist bewusst persistent. Bei Verdacht auf Kompromittierung:
  neue Werte setzen (PG-Passwort: `ALTER ROLE hcc PASSWORD …` +
  `hcc.env`-Update + Service-Neustart) und Alt-Secrets für widerrufen
  erklären — nicht „zurückrollen“.
- **Bootstrap-Token:** bleibt nach Nutzung in `hcc.env` (D3). Rotation:
  neuen Wert in `hcc.env` setzen + Neustart; `/auth/bootstrap` ist ohnehin
  nur ohne User nutzbar.
- **Sicherheitsvorfall im LXC:** L4 + Secrets-Reset + (falls Proxmox-API-
  Tokens im Einsatz waren, s. Playbook §3) Token-Rotation.

## 8. Nach jedem Rollback (Pflicht)

1. `deploy-lxc.sh --list` → aktive Release korrekt markiert.
2. Healthchecks (Playbook §13.2/13.4) grün.
3. Smoke-Test bei nicht-trivialen Rollbacks (L3/L4 immer).
4. Vorfall-Notiz: Trigger, Ebene, Zeit, Ergebnis — in die
   Abnahme-Doku `R1-acceptance-checklist.md` (Bereich D) oder ein
   Betriebsprotokoll.
5. Falls Rollback auf L3/L4: frisches Backup + `pg_dump` (Punkt 0 neu).
