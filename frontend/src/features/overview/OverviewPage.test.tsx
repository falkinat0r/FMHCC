import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";

import OverviewPage from "./OverviewPage";
import { AuthProvider } from "../auth/AuthProvider";
import {
  FIXTURE_AUDIT,
  FIXTURE_INTEGRATIONS,
  FIXTURE_RESOURCES,
  FIXTURE_USER,
  pagedFixture,
} from "../../api/fixtures";
import type { Role } from "../../api/types";
import {
  createTestQueryClient,
  errorResponse,
  fetchRouter,
  jsonResponse,
} from "../../test/test-utils";

function stubSession(role: Role) {
  return {
    "/auth/me": jsonResponse(200, {
      ...FIXTURE_USER,
      role,
      username: `demo-${role}`,
    }),
  };
}

type RouteStub = Response | ((path: string) => Response);

function renderOverview(
  role: Role,
  extraRoutes: Record<string, RouteStub> = {},
) {
  vi.stubGlobal(
    "fetch",
    fetchRouter({
      ...stubSession(role),
      ...extraRoutes,
    }),
  );
  const queryClient = createTestQueryClient();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <OverviewPage />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return result;
}

async function kpiCard(title: string): Promise<HTMLElement> {
  // Title-Span existiert erst, wenn die Ressourcen geladen sind (sonst Skeleton)
  const label = await screen.findByText(title, { selector: "span" });
  const card = label.closest(".rounded-lg");
  if (card === null) throw new Error(`KPI-Karte '${title}' nicht gefunden`);
  return card as HTMLElement;
}

describe("OverviewPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("zeigt Daten aus den echten Endpunkten (KPIs, Integrationen, Events)", async () => {
    renderOverview("admin", {
      "/resources": jsonResponse(200, pagedFixture(FIXTURE_RESOURCES, 1, 200)),
      "/integrations": jsonResponse(
        200,
        pagedFixture(FIXTURE_INTEGRATIONS, 1, 50),
      ),
      "/audit": jsonResponse(200, pagedFixture(FIXTURE_AUDIT, 1, 8)),
    });

    // KPIs aus der Ressourcenliste
    expect(within(await kpiCard("Hosts")).getByText("1")).toBeInTheDocument();
    expect(within(await kpiCard("VMs")).getByText("2")).toBeInTheDocument();
    expect(within(await kpiCard("LXC")).getByText("1")).toBeInTheDocument();
    expect(within(await kpiCard("Container")).getByText("1")).toBeInTheDocument();
    expect(within(await kpiCard("Container")).getByText("1 down")).toBeInTheDocument();
    expect(within(await kpiCard("Storage")).getByText("2")).toBeInTheDocument();

    // Integrationen (read-only Health-Panel)
    await screen.findByText("Demo Proxmox (Fixture)");
    expect(screen.getByText("demo-monitoring")).toBeInTheDocument();
    expect(screen.getByText("demo-pihole")).toBeInTheDocument();

    // Audit-Events (admin)
    expect(await screen.findByText("integrations.verify")).toBeInTheDocument();

    // Fehlende Funktionen bleiben ehrlich "nicht verfügbar"
    expect(
      screen.getByText(/Keine Alert-Quelle im aktuellen API-Vertrag/),
    ).toBeInTheDocument();
  });

  it("zeigt für nicht-admin keine Audit-Events, sondern den RBAC-Hinweis", async () => {
    renderOverview("viewer", {
      "/resources": jsonResponse(200, pagedFixture(FIXTURE_RESOURCES, 1, 200)),
      "/integrations": jsonResponse(
        200,
        pagedFixture(FIXTURE_INTEGRATIONS, 1, 50),
      ),
      // Das Panel holt das Audit nicht dar; 403 wäre serverseitig korrekt —
      // UI zeigt den Hinweis, ohne Event-Daten anzuzeigen.
      "/audit": errorResponse(403, "forbidden", "admin erforderlich"),
    });

    await screen.findByText("Demo Proxmox (Fixture)");
    expect(
      screen.getByText(
        "Audit-Log ist nur für die Rolle admin lesbar (serverseitige RBAC-Prüfung).",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("integrations.verify")).not.toBeInTheDocument();
  });

  it("zeigt den Leerzustand ohne Fixtures", async () => {
    const empty = (items: never[]) =>
      jsonResponse(200, pagedFixture(items, 1, 50));
    renderOverview("admin", {
      "/resources": empty([]),
      "/integrations": empty([]),
      "/audit": empty([]),
    });

    // KPIs: 0 — keine erfundenen Werte
    expect(within(await kpiCard("Hosts")).getByText("0")).toBeInTheDocument();
    expect(within(await kpiCard("VMs")).getByText("0")).toBeInTheDocument();

    await screen.findByText("Noch keine Integrationen konfiguriert.");
    expect(await screen.findByText("Keine Audit-Events vorhanden.")).toBeInTheDocument();
  });

  it("zeigt Fehler mit Retry und Request-ID (Error-Envelope)", async () => {
    const boom = errorResponse(500, "internal", "Interner Fehler", "req-err-42");
    renderOverview("admin", {
      "/resources": boom,
      "/integrations": boom,
      "/audit": boom,
    });

    const alerts = await screen.findAllByRole("alert");
    expect(alerts.length).toBeGreaterThanOrEqual(2);
    expect(alerts[0]).toHaveTextContent("Interner Fehler");
    expect(screen.getAllByText("req-err-42").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("button", { name: "Erneut versuchen" }).length).toBeGreaterThanOrEqual(1);
  });

  it("zeigt Ladezustände, solange Requests pendeln", () => {
    vi.stubGlobal("fetch", () => new Promise<Response>(() => {}));
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <AuthProvider>
          <OverviewPage />
        </AuthProvider>
      </QueryClientProvider>,
    );
    // Mindestens ein Panel mit aria-busy (z. B. Integration-Panel)
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
  });
});
