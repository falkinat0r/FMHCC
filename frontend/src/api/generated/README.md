# `frontend/src/api/generated/` — generierte Typen (nur lesbar)

Die TypeScript-Typen werden aus dem verbindlichen OpenAPI-Contract
generiert — **nie** handgeschrieben geändert:

```bash
# aus frontend/, Node >= 20.19
npx openapi-typescript ../backend/contracts/openapi.v1.json -o src/api/generated/schema.ts
```

Quelldokument: [`backend/contracts/openapi.v1.json`](../../backend/contracts/openapi.v1.json)
(frozen Contract-Snapshot, R0).

## Regeln

- Agent 2 hat **keinen Schreibzugriff** auf dieses Verzeichnis
  (`docs/PARALLEL_WORKFLOW.md`).
- Contract-Änderungen laufen ausschließlich über
  `docs/api-contracts.md` Abschnitt 6 (Proposal + Snapshot-Regenerierung).
- `src/api/client.ts` (R0-Shell) nutzt interimär handgeschriebene
  Schemas; Agent 2 ersetzt diese durch die generierten Typen, ohne die
  Client-Semantik (CSRF Double-Submit, Error-Envelope) zu ändern.
