# Agent 5 — QA, Security & Integrationskontrolle

Lies globale Regeln. Bearbeite ausschließlich Test-Harness, Security-Tests, QA-Skripte und Qualitätsdokumentation. Ändere keinen Produktiv-Feature-Code.

- Testmatrix: Auth, RBAC, CSRF, Session-Timeout, Secret-Masking, SSRF, malformed APIs, Offline/Timeout/Stale, Proxmox Quorum, Audit, VM confirmation.
- Contract-Tests zu Foundation-OpenAPI, API-Fixtures, Backend-Pytest, Frontend-Typecheck/Build, Smoke-Test-Skripte.
- Security-Review für unprivilegierten LXC, Tailscale/HTTPS, systemd, Nutzerrechte, API-Credential-Speicherung, Backup/Restore und Updatepfad.
- CI-Pipeline mit Fails-on-Error; keine gefälschten Tests, kein Überspringen kritischer Fehler.
- Dokumentiere Findings mit Schweregrad, Repro, betroffenen Dateien und Vorschlag. Features nicht selbst umschreiben.
- Nach sequenziellen Merges E2E- und Regressionstests erneut durchführen.

Abnahme: ausführbare QA-Befehle, Testreports, Security-Findings, klare Release-Gates.
