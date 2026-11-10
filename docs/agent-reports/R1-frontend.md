# R1 Frontend — Agent-Report (Agent 2)

**Datum:** 2026-11-10
**Branch:** `feature/frontend` (Worktree `C:\Users\muehleisen\Documents\hcc-frontend`)
**Basis:** `feature/frontend` aus `c86c3a4` (Foundation-Handoff, R0-Shell)
**Commit:** `c37c3c0` (in `feature/frontend`, kein Merge nach `main`) —
dieser Report folgt als separater Docs-Commit, da der Hash erst nach dem
Commit bekannt ist.
**Vertrag:** `backend/contracts/openapi.v1.json` (frozen R0) — **nicht** geändert

## 1. Was gebaut wurde

Vollständige Operations-UI (Dark-Mode, Tailwind v4, shadcn-artige Primitives,
TanStack Query v5, React Flow, Recharts, Lucide), strikt gegen den
R0-Vertrag:

| Bereich | Seiten | Endpunkte (alle aus dem frozen Vertrag) |
| --- | --- | --- |
| Auth | `/login` | `POST /auth/login`, `GET /auth/me`, `POST /auth/logout` |
| Overview | `/` | `GET /resources`, `GET /integrations`, `GET /audit` (admin) |
| Compute | `/compute`, `/resources/{id}` | `GET /resources`, `GET /resources/{id}` |
| Topologie | `/topology` | `GET /resources`, `GET /resources/{id}` (Relationen, limitiert 200) |
| Monitoring | `/monitoring` | `GET /integrations`, `GET /resources`, `GET /audit` (admin) — Metriken/Alerts: **keine Endpunkte** (Proposal) |
| Integrationen | `/integrations`, `/integrations/{id}` | `GET /integrations(/{id})`, `PUT /integrations/{id}` (admin+CSRF), `DELETE /integrations/{id}` (admin+CSRF), `POST …/verify` (admin+CSRF) |
| Audit | `/audit` | `GET /audit` (admin, RBAC-gespiegelt) |
| Einstellungen | `/settings` | `GET /auth/me`, `GET/POST /users`, `PATCH /users/{id}` (admin+CSRF) |

### Zentrale Design-Regeln (umgesetzt)
- **Kein erfundener Endpunkt:** Alles, was der Vertrag nicht kennt
  (VM-/LXC-Aktionen, Metriken, Alerts, Bulk-Relationen, Passwortwechsel), ist
  in der UI explizit als „nicht verfügbar / blockiert" gekennzeichnet und
  referenziert das zugehörige Proposal. Es gibt keine Mock-Chart-Daten in
  Produktion.
- **Zustände:** `loading | error | empty | not_configured | unknown` als
  einheitliche `StatePanel` (Error inkl. Request-ID aus der Error-Envelope,
  Retry-Button).
- **RBAC gespiegelt (Server bleibt verbindlich):** Nav (Audit nur admin),
  Aktionsknöpfe (operator+), Integrations-/User-Verwaltung (admin),
  Audit-Panel. Die UI verbirgt/aktiviert nur — jede Endpunkt-Autorisierung
  bleibt serverseitig.
- **CSRF Double-Submit:** Client setzt `X-CSRF-Token` generisch für alle
  state-aendernden Requests (aus `hcc_csrf`-Cookie); `credentials: include`.
- **Typen:** generiert via `npm run gen:types` (openapi-typescript) in
  `src/api/generated/schema.ts`; `src/api/types.ts` aliasiert. Generierte
  Typen unverändert (nur lesbar, AGENTS.md/PARALLEL_WORKFLOW).
- **Evidenz in der Topologie:** Kanten nur aus `relations` des
  Detail-Endpoints; `api` (solid), `manual` (gestrichelt), `inferred`
  (gepunktet, als vermutet gekennzeichnet); Beziehungen ohne sichtbare
  Endpunkte werden gezählt, nicht gezeichnet. Positions-Persistierung nur
  lokal (localStorage, Key `hcc.topology.positions.v1`) — kein
  Layout-Endpunkt im Vertrag.
  *Implementierungsdetail (React Flow 11.x):* Kanten werden nur gerendert,
  wenn am Custom Node unsichtbare `<Handle>`-Elemente (source Bottom /
  target Top) vorhanden sind — ohne werden Kanten intern verworfen
  (Error 008). Die Topologie ist read-only (`nodesConnectable={false}`,
  `onConnect` leer), daher dienen die Handles (`opacity-0`) nur als
  Verankerungspunkte. Verifiziert: 10/10 Nodes mit Handles, 8 Kanten im
  Store (Fixture-Modus).
- **DEV-FIXTURE-Modus:** `?dev=fixture` oder `VITE_HCC_DEV_FIXTURE=true` +
  `&role=viewer|operator|admin`; dauerhafter `DevBanner`; alle Fixtures
  `demo-*`-geprägt, `source=manual`, ohne echte Namen/Daten (AGENTS.md §7).
- **Fehlerbehandlung:** zentrales `ApiRequestError`
  (`status/code/requestId/message` aus der Error-Envelope);
  `ErrorBoundary` auf App-Ebene; TanStack Query mit `retry: 1`,
  `refetchOnWindowFocus: false`.

## 2. Funktionsstatus

| Funktion | Status |
| --- | --- |
| Login / Session / Logout | **funktional** (gegen echte Endpunkte) |
| Overview-KPIs, Integration-Health, Audit-Events (admin) | **funktional** |
| Compute-Listen (Hosts/VMs/LXC/Container), Filter, Paging | **funktional** |
| Ressourcen-Detail (Status, Payload, Relationen mit Evidenz) | **funktional** |
| Topologie (Knoten/Kanten, Filter, Layout-Persistierung) | **funktional**, limitiert 200 Ressourcen (Proposal `frontend-topology-bulk-relations`) |
| Integrationen: Anlegen/Konfigurieren/Löschen/Verify | **funktional** (Verify antwortet in R0 `501 not_implemented` — wird ehrlich angezeigt) |
| Audit-Log (admin) | **funktional** |
| Benutzerverwaltung (admin) | **funktional** |
| VM-/LXC-Aktionen (start/stop/reboot) | **blockiert** — kein Endpunkt im Vertrag (Proposal `frontend-vm-actions`) |
| Metriken (CPU/RAM, 1 h … 30 d) | **blockiert** — kein Endpunkt im Vertrag (Proposal `frontend-metrics-and-alerts`) |
| Alerts | **blockiert** — kein Endpunkt im Vertrag (Proposal `frontend-metrics-and-alerts`) |
| Passwortwechsel | **blockiert** — kein Endpunkt im Vertrag (Proposal `frontend-password-change`) |

## 3. Getestete Schritte (konkret ausgeführt, Windows/Node 22.14)

| Befehl (in `frontend/`) | Ergebnis |
| --- | --- |
| `npx tsc -b --noEmit` | **sauber** (0 Fehler) |
| `npx eslint .` | **sauber** (0 Fehler, 0 Warnings) |
| `npx vitest run` | **94 passed / 0 failed** (13 Test-Dateien) |
| `npm run build` | **erfolgreich** (`dist/`, 2157 Module; Hinweis: 947 kB JS-Bundle, gzip 287 kB — Code-Splitting als optionales Follow-up) |
| `npm run gen:types` | Snapshot `src/api/generated/schema.ts` regeneriert (identisch zum frozen Contract) |

### Testabdeckung (Auszug)
- **API-Client:** CSRF-Double-Submit (POST/PUT mit Body, nicht bei GET),
  Error-Envelope-Parsing, `ApiRequestError`, `buildQuery` (leere Parameter
  werden weggelassen).
- **Auth:** `AuthProvider` (loading/guest/user, 401→guest, kein erfundener
  User), `RequireAuth` (Redirect `/login` mit Return-URL, nur mit Session
  Inhalt).
- **Navigation (Sidebar):** alle 7 Einträge + Routen, `aria-current` auf
  aktivem Eintrag, Audit-Log für admin sichtbar / für viewer+operator
  ausgeblendet.
- **OverviewPage:** Daten-Zustand (KPIs aus echten Endpunkten,
  Integration-Health, Audit-Events für admin, Alerts ehrlich „nicht
  verfügbar"), RBAC-Zustand (kein Audit für nicht-admin), Leerzustand
  (keine Fixtures als Echt-Daten), Fehlerzustand (Error-Envelope + Retry +
  Request-ID), Ladezustand.
- **Compute:** ResourceDetail lädt Detail aus `GET /resources/{id}`;
  operator sieht Start/Shutdown/Reboot, viewer nur RBAC-Hinweis;
  Action-Dialog blockiert (kein Endpunkt im R0-Vertrag, kein Bestätigen).
- **IntegrationsPage:** Liste (Adapter/Status/Capabilities/last_error),
  admin sieht Anlegen-Dialog (CSRF-geschütztes PUT), viewer nicht.
- **Topologie-Modell:** Knoten 1:1 aus Ressourcen (keine erfundenen), Kanten
  1:1 aus dokumentierten Relationen (keine erfundenen Verbindungen),
  Evidenz-Erhalt (api/manual/inferred), Deduplizierung, „skipped"-Zählung
  bei fehlenden Endpunkten, deterministisches Layout.
- **StatusBadge:** alle 5 fachlichen Zustände, unbekannter Wert → `unknown`
  (kein Ratespiel).
- **StatePanel:** loading/error/empty/not_configured, `describeApiError`,
  `queryStatePanel`.
- **Fixtures/DEV-Modus:** `demo-*`-Präfix-Disziplin, `pagedFixture`
  (Klammern/Seitenberechnung), `fixtureMetricSeries` (deterministisch,
  plausible Werte), `isDevFixture` (URL-Parameter + Env-Variable).
- **Formatierung:** `timeAgo`/`ageInHours`/`formatCount`/`formatDateTime`
  (keine erfundenen Werte, `n/v` bei Fehlen).

## 4. Offene Risiken / Grenzen

1. **Bundle-Größe:** Einzel-Chunk 947 kB (gzip 287 kB). Recharts + React Flow
   sind schwer; für Homelab-Größen vertretbar, Code-Splitting
   (`build.rollupOptions`) ist ein optionales Follow-up (keine
   Funktionsbeeinträchtigung).
2. **Topologie-Limit 200:** Bis zur Bulk-Relation-Proposal-Umsetzung wird die
   Topologie auf die ersten 200 Ressourcen limitiert (in der UI sichtbar
   gekennzeichnet, `useResourceDetailsAll`).
3. **Metriken/Alerts/Aktionen/Passwortwechsel:** Blockiert (keine Endpunkte im
   R0-Vertrag) — UI zeigt dies ehrlich an, keine Mocks. Siehe Proposals.
4. **Kein Node.js in R0-Handoff:** R0-Shell war `code_only`; dieser Report
   schließt diese Lücke (alle vier Prüfungen gelaufen, siehe §3).
5. **`core.autocrlf` nicht gesetzt:** Git zeigt LF→CRLF-Warnings (Windows) —
   funktional irrelevant, bei Bedarf Repo-weit normalisieren.

## 5. Betroffene Dateien

**Erstellt (neue Features):**
- `frontend/src/api/query.ts`, `frontend/src/api/types.ts`,
  `frontend/src/api/dev.ts`, `frontend/src/api/fixtures.ts`,
  `frontend/src/api/generated/` (regeneriert)
- `frontend/src/lib/{cn,format,status,permissions}.ts`
- `frontend/src/components/ui/{button,badge,card,input,label,select,table,separator,skeleton,dialog,tabs}.tsx`
- `frontend/src/components/common/{StatusBadge,StatePanel,Pagination,ErrorBoundary,JsonView,DevBanner,PageHeader,MetricChart}.tsx`
- `frontend/src/components/layout/{nav,Sidebar,Breadcrumbs,GlobalSearch,UserMenu,Header,AppShell}.tsx`
- `frontend/src/features/auth/{AuthProvider,RequireAuth,LoginPage}.tsx`
- `frontend/src/features/overview/OverviewPage.tsx`
- `frontend/src/features/compute/{ComputePage,ActionDialog,ResourceDetailPage}.tsx`
- `frontend/src/features/topology/{model,TopologyPage}.tsx`
- `frontend/src/features/integrations/{adapterInfo,IntegrationsPage,IntegrationDetailPage}.tsx`
- `frontend/src/features/monitoring/MonitoringPage.tsx`
- `frontend/src/features/audit/AuditPage.tsx`
- `frontend/src/features/settings/SettingsPage.tsx`
- `frontend/src/App.tsx`, `frontend/src/main.tsx` (neu)

**Tests (neue):**
- `frontend/src/test/{test-utils.tsx,jest-dom.d.ts}`
- `frontend/src/api/{client,dev,fixtures}.test.ts` (client erweitert um buildQuery)
- `frontend/src/lib/format.test.ts`
- `frontend/src/components/common/{StatusBadge,StatePanel}.test.tsx`
- `frontend/src/components/layout/Sidebar.test.tsx`
- `frontend/src/features/auth/AuthProvider.test.tsx`
- `frontend/src/features/overview/OverviewPage.test.tsx`
- `frontend/src/features/compute/{ActionDialog,ResourceDetailPage}.test.tsx`
- `frontend/src/features/integrations/IntegrationsPage.test.tsx`
- `frontend/src/features/topology/model.test.ts`

**Konfiguration (angepasst):**
- `frontend/eslint.config.js` (typescript-eslint + Parser, React-Plugin)
- `frontend/vite.config.ts` (Vitest-Config: jsdom, setup, globals)
- `frontend/package.json` (Deps: @tanstack/react-query, reactflow, recharts,
  lucide-react, clsx, tailwind-merge; Dev: @tailwindcss/vite,
  @testing-library/*, jsdom, vitest, typescript-eslint)

**Doku (neue):**
- `docs/proposals/frontend-vm-actions.md`
- `docs/proposals/frontend-metrics-and-alerts.md`
- `docs/proposals/frontend-topology-bulk-relations.md`
- `docs/proposals/frontend-password-change.md`
- `docs/agent-reports/R1-frontend.md` (dieses Dokument)

**Entfernt (ersetzt durch neue Features):**
- `frontend/src/pages/{Dashboard,Login}.tsx` (R0-Shell)

## 6. Integrationshinweise

1. **Review:** `git diff c86c3a4..c37c3c0` (Worktree `hcc-frontend`), Fokus:
   `src/api/query.ts` (Endpunkt-Abbildung), `src/api/client.ts` (CSRF/
   Envelope), `src/features/` (Feature-Logik), Proposals.
2. **Merge in `main`** durch Betreiber nach Review (kein Auto-Merge,
   AGENTS.md §3/4).
3. **Parallele Agenten:** Proxmox (Agent 3) kann die
   `resource_type`/`status`-Werte aus dem frozen Contract verwenden;
   Telemetry (Agent 4) sollte die Metriken-/Alerts-Proposal-Formate
   (`MetricSeries`, `AlertOut`) beachten, wenn diese umgesetzt werden.
4. **Contract-Änderungen** ausschließlich über die Proposals +
   Snapshot-Regenerierung (`scripts/generate-openapi.py`).
5. **Deployment:** `frontend/dist` wird von nginx ausgeliefert
   (`deploy/nginx/hcc.conf`); `/api/` → Loopback 8000. DEV-FIXTURE-Modus ist
   **nur** für Entwicklung (`?dev=fixture`), niemals in Produktion aktivieren.
