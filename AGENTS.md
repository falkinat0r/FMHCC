# Homelab Control Center — verbindliche Projektregeln

1. Lies `MASTER_PROMPT.md` und die für die Aufgabe relevante Datei unter `agent-tasks/` sowie `docs/PARALLEL_WORKFLOW.md`. Behandle die dortigen API-/Dateibesitz-Grenzen als verpflichtend.
2. Arbeite nur im eigenen Worktree und Branch. Prüfe `git branch --show-current`, `pwd` und `git status` vor jeder Änderung. Niemals in `main` entwickeln. Keine parallele Arbeit im gleichen Checkout.
3. Kein `git reset --hard`, `git clean -fd`, `push --force` oder automatischer Merge. Nur eigene Dateien committen. Keine stillschweigende Änderung an gemeinsamen Contracts, Migrationen oder globalen Abhängigkeiten.
4. Falls ein Contract angepasst werden muss, dokumentiere Änderungsvorschlag in `docs/proposals/<agent>-<topic>.md` und blockiere die betroffene Funktion, statt konkurrierende Implementierungen zu schaffen.
5. Keine Secrets, Tokens, Infrastruktur-Credentials oder privaten Daten in Code, Tests, Logs und Commits. Keine produktiven Infrastrukturänderungen ohne explizite Freigabe.
6. KI-Funktionen sind **nicht im Scope**. Keine LLM-/LiteLLM-/Agent-Integration in der Anwendung entwickeln.
7. Nutzer sichtbare Daten sind echt oder klar als Fixture/Demo gekennzeichnet; fehlende Daten sind `unknown`/`not_configured`, niemals zufällige Erfolgswerte.
8. Backend zuerst RBAC, Audit, Inputvalidierung und Fehlerbehandlung berücksichtigen. Keine offene Shell-API, keine unsicheren Docker-Sockets.
9. Halte Typprüfung, Tests, Lint und Build lauffähig. Melde konkret ausgeführte Befehle und Ergebnisse. Testfehler nicht umgehen.
10. Am Ende: Liste betroffener Dateien, Implementierungen, getesteter Schritte, offener Risiken, Commit-Hash und Integrationshinweise.
