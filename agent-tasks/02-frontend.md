# Agent 2 — Frontend & Operations UI

Lies globale Regeln. Bearbeite nur die vereinbarten Frontend-Verzeichnisse.

- React/TS strict, responsive Dark-Mode-Operations-UI mit Sidebar Overview, Compute, Storage, Network, Containers, Monitoring, Alerts, Settings.
- Keine AI-Sektion.
- UI-Daten über eingefrorene OpenAPI-Contracts/generated client oder versionierte Fixtures; nie imaginäre Endpoints.
- Einheitliche Loading/Offline/Unknown/Not-configured/Stale/Error-Zustände; präzise Zeitstempel und Quelllabels.
- Overview-Karten, Compute-Liste, Detailansicht, Filter, Suchfeld, beständige Navigation; React Flow Topologie-Komponente zunächst gegen vereinbarte Ressourcen-/Edge-Fixtures.
- VM-Aktionen nur mit Confirmations und Rollenabhängigkeit; Backend erzwingt RBAC tatsächlich.
- A11y, Keyboard-Navigation, Komponenten-Tests, Build/Typecheck.

Abnahme: vollständiger statischer Build, korrekte Fehler-/Leerstati, verlässliche Navigations- und Komponententests.
