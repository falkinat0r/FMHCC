# Agent 4 — Monitoring und weitere Adapter

Lies globale Regeln. Bearbeite ausschließlich die zugewiesenen Monitoring-/Integrationsverzeichnisse.

- Discovery-/Health-Adapter für vorhandenes Prometheus, Grafana, Uptime Kuma, Netdata, optional Loki; keine automatische Installation.
- Gültige, versionsabhängige API-Fähigkeiten abfragen. Integration nicht erreichbar → `unknown` / `not_configured`, niemals erfundener Status.
- Metriken für Zeiträume 1h/6h/24h/7d/30d mit definierten Einheiten, Timeouts, Source-Freshness und Ziel-Labels.
- Ereignisnormalisierung und Alerting-Integration; deterministische Regeln, keine LLM/AI-Features.
- Danach unabhängige read-only Adapter für Pi-hole, TrueNAS, Tailscale, Docker; version- und capability-gated. Für Docker niemals ungeschützten TCP-Socket öffnen.
- Pro Adapter Fixtures, Timeout-/Error-/Security-Tests.

Abnahme: mindestens Prometheus- und Pi-hole-Testadapter über vereinbarte Contracts; andere Adapter modular und transparent als offen dokumentiert, falls nicht fertig.
