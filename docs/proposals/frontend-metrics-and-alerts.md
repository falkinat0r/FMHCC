# Proposal: Metriken- und Alert-Endpunkte (Agent: frontend)

**Status:** offen — Monitoring-Oberfläche zeigt Metriken/Alerts als
„nicht verfügbar" (kein Mock, keine erfundenen Charts).
**Betreff:** `/api/v1` kennt weder Metrik- noch Alert-Endpunkte; die
Monitoring-Seite (`frontend/src/features/monitoring/MonitoringPage.tsx`) und die
Ressourcen-Detailseite können daher keine CPU/RAM-Historie (1 h … 30 d) oder
regelmäßige Alerts darstellen.

## Motivation

- MASTER_PROMPT verlangt Monitoring mit Metriken (CPU/RAM, Historie) und
  Alerts, auf Basis der bestehenden Prometheus-/Grafana-Anbindung.
- Die UI ist für die Endpunkte vorbereitet (Recharts-Chart `MetricChart`,
  Zeitraum-Selektion, Quellkennzeichnung), liefert in Produktion aber den
  Status `{ available: false }` — bewusst, da das R0-Vertrag sie nicht kennt.
- `adapter = monitoring` (frozen Enum) deckt Prometheus/Grafana ab; ein
  `VerifyResponse` mit `capabilities.prometheus/grafana` ist bereits vorhanden.

## Vorschlag (Diff-Plan)

Neue Pfade:

| Methode | Pfad | Berechtigung | Beschreibung |
| ------- | ---- | ------------ | ------------ |
| GET | `/api/v1/resources/{resource_id}/metrics?metric=cpu\|memory&range=1h\|6h\|24h\|7d\|30d` | viewer+ (`resources.read`) | Metrikreihe aus der konfigurierten Monitoring-Quelle (Prometheus `query_range`); Response: `MetricSeries` |
| GET | `/api/v1/alerts` | viewer+ (`alerts.read`) | Aktive und zuletzt behobene Alerts (aus Prometheus `alerts`/`alertmanagers`), paged |

Schemata:

- `MetricSeries`:
  ```json
  {
    "available": true,
    "reason": null,
    "unit": "%",
    "source": "prometheus:https://monitoring.example:9090",
    "points": [{ "ts": "2026-11-10T11:00:00Z", "value": 12.5 }]
  }
  ```
  `available: false` + `reason` (z. B. `monitoring_not_configured`,
  `no_data_for_range`) ist ein regulärer 200-Zustand — die UI zeigt dann
  exakt die `reason` an (keine erfundenen Punkte).
- `AlertOut`: `{ id, name, state: "firing"|"resolved", resource_id: string|null,
  started_at, resolved_at: string|null, labels: {} }`.

Voraussetzungen (Backend):
- Monitoring-Adapter (Agent 4/telemetry) liefert Metriken-Auslese über die
  Prometheus-HTTP-API (`/api/v1/query_range`); keine Grafana-API in R1 nötig
  (Grafana bleibt Visualisierung).
- Mapping `resource_id → Prometheus-Target/Instanz` über das Inventar
  (`payload` der host-/vm-/lxc-Ressourcen, z. B. `instance`-Label).

## Impact

- **Frontend:** `useMetricSeries` (`src/api/query.ts`) holt dann den echten
  Endpunkt statt des `{ available: false }`-Platzhalters; Alerts-Panel auf der
  Monitoring-Seite bindet an `/alerts`. Keine UI-Strukturänderung nötig.
- **RBAC:** `alerts.read` (viewer+) — Alerts sind Lesedaten.
- **Performance:** `range=30d` mit grobem Step (5–15 min), Cache pro
  (resource, metric, range) — max. 200 Punkte pro Serie, wie von der UI
  erwartet.
- **Kein Secret-Leak:** Base-URLs/Token der Monitoring-Integration bleiben
  serverseitig (`secret_ref`); in `MetricSeries.source` nur der
  nicht-sensible Namen der Quelle.
