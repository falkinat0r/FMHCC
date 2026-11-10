import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import IntegrationsPage from "./IntegrationsPage";
import { AuthProvider } from "../auth/AuthProvider";
import { FIXTURE_INTEGRATIONS, FIXTURE_USER, pagedFixture } from "../../api/fixtures";
import type { Role } from "../../api/types";
import {
  createTestQueryClient,
  fetchRouter,
  jsonResponse,
} from "../../test/test-utils";

function renderIntegrationsForRole(role: Role) {
  vi.stubGlobal(
    "fetch",
    fetchRouter({
      "/auth/me": jsonResponse(200, {
        ...FIXTURE_USER,
        role,
        username: `demo-${role}`,
      }),
      "/integrations": jsonResponse(200, pagedFixture(FIXTURE_INTEGRATIONS, 1, 50)),
    }),
  );
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/integrations"]}>
        <AuthProvider>
          <IntegrationsPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IntegrationsPage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("listet Integrationen mit Adapter, Status und Capabilities", async () => {
    renderIntegrationsForRole("viewer");

    await screen.findByText("Demo Proxmox (Fixture)");
    expect(screen.getByText("Demo Monitoring (Fixture)")).toBeInTheDocument();
    expect(screen.getByText("Demo Pi-hole (Fixture)")).toBeInTheDocument();

    // Capabilities aus dem Contract, nicht erfunden (✓ = true aus dem API-Feld)
    expect(screen.getByText(/nodes:✓/)).toBeInTheDocument();
    // Degradierter Adapter zeigt den letzten Fehler ehrlich an
    expect(
      screen.getByText("fixture: simulierter Timeout (keine echte Ursache)"),
    ).toBeInTheDocument();
  });

  it("zeigt admin den Anlegen-Button (CSRF-geschütztes PUT)", async () => {
    renderIntegrationsForRole("admin");
    const button = await screen.findByRole("button", {
      name: "Neue Integration",
    });

    fireEvent.click(button);
    expect(await screen.findByRole("dialog")).toHaveAccessibleName(
      "Neue Integration anlegen",
    );
    expect(
      screen.getByLabelText("Integration-ID (Slug)"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Secret-Ref (Name der Env-Variable)"),
    ).toBeInTheDocument();
  });

  it("versteckt Verwaltungsaktionen für viewer (RBAC, serverseitig verbindlich)", async () => {
    renderIntegrationsForRole("viewer");
    await screen.findByText("Demo Proxmox (Fixture)");
    expect(
      screen.queryByRole("button", { name: "Neue Integration" }),
    ).not.toBeInTheDocument();
  });
});
