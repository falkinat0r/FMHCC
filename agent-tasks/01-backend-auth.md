# Agent 1 — Backend, Auth und RBAC

Lies globale Regeln. Bearbeite nur Backend-Auth-/User-Module und zugehörige Tests im vereinbarten Besitzbereich.

- Implementiere Argon2id-Login, serverseitige Session-Verwaltung, Cookie- und CSRF-Schutz; keine fest eingebauten Admin-Credentials.
- Rollen Viewer, Operator, Admin mit zentralem Berechtigungsprüfer; Tests für unautorisierte/unerlaubte Aktionen.
- Einmalige Admin-Bootstrap-Prozedur; konfigurierbare Session-Lifetime und Logout.
- API-Errorformat und Auth-Routen nach **bestehendem Foundation-Contract**; keine eigenmächtigen Contract-Änderungen.
- Audit-Hooks auf bestehende Schnittstellen; sichere Log-Maskierung und Rate-Limiting des Logins.
- Schreibe Unit-/Integrationstests. Committe eigene Änderungen ohne Merge.

Abnahme: Login/Logout, rollenbasierte Zugriffstests, abgelaufene Session, falsche Credentials, CSRF-Abwehr und dokumentierte Setup-Schritte.
