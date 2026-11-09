# HCC 2.0 — OpenCode Starterpaket

Dateien:
- `MASTER_PROMPT.md`: projektspezifischer Masterauftrag, Scope und Releaseplan.
- `AGENTS.md`: permanente, automatisch geladene Projektregeln für OpenCode.
- `docs/DEPLOYMENT_PLAYBOOK.md`: LXC-/Tailscale-Vorbereitung, Sicherheit, Deployment-Vertrag, Abnahmetests.
- `docs/PARALLEL_WORKFLOW.md`: Worktrees, Rollen, Merge und GPU-Durchsatz.
- `agent-tasks/01-...05-...`: fünf einzeln ausführbare OpenCode-Aufträge.

**Wichtig:** Vor fünf parallelen Sessions erst Foundation in einer einzelnen Session implementieren und gemeinsame API-Verträge committen. Anschließend separate Worktrees pro Agent.

**Keine produktive Installation erfolgt durch diese Dateien.** Der initiale LXC-Anlegebefehl ist ein überprüfbares Beispiel mit expliziten Platzhaltern. Realen Proxmox-Zugriff und Schreibaktionen erst nach Freigabe.
