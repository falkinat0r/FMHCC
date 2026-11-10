import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import { Sidebar } from "./Sidebar";
import { AuthProvider, useAuth } from "../../features/auth/AuthProvider";
import { FIXTURE_USER } from "../../api/fixtures";
import type { Role } from "../../api/types";
import { createTestQueryClient, fetchRouter, jsonResponse } from "../../test/test-utils";

/** Zeigt die aufgelöste Session — dient als Warte-Kriterium in Tests. */
function RoleProbe() {
  const { status, user } = useAuth();
  return (
    <p data-testid="role-probe">
      {status}:{user?.role ?? "none"}
    </p>
  );
}

function renderSidebarForRole(role: Role, route = "/compute") {
  vi.stubGlobal(
    "fetch",
    fetchRouter({
      "/auth/me": jsonResponse(200, {
        ...FIXTURE_USER,
        role,
        username: `demo-${role}`,
      }),
    }),
  );
  const queryClient = createTestQueryClient();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <RoleProbe />
          <Sidebar />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return result;
}

describe("Sidebar-Navigation", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("zeigt alle Bereiche inkl. Audit für admin an", async () => {
    renderSidebarForRole("admin");
    await screen.findByText("user:admin");

    for (const label of [
      "Dashboard",
      "Compute",
      "Topologie",
      "Monitoring",
      "Integrationen",
      "Audit-Log",
      "Einstellungen",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
  });

  it("versteckt das Audit-Log für nicht-admin-Rollen (RBAC)", async () => {
    renderSidebarForRole("viewer");
    await screen.findByText("user:viewer");

    expect(
      screen.queryByRole("link", { name: "Audit-Log" }),
    ).not.toBeInTheDocument();
    // Die restlichen Einträge bleiben sichtbar
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Einstellungen" })).toBeInTheDocument();
  });

  it("markiert den aktiven Eintrag mit aria-current", async () => {
    renderSidebarForRole("operator", "/topology");
    await screen.findByText("user:operator");

    expect(screen.getByRole("link", { name: "Topologie" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: "Compute" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("führt alle Einträge zu den erwarteten Routen", async () => {
    renderSidebarForRole("admin");
    await screen.findByText("user:admin");

    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.getByRole("link", { name: "Compute" })).toHaveAttribute(
      "href",
      "/compute",
    );
    expect(screen.getByRole("link", { name: "Topologie" })).toHaveAttribute(
      "href",
      "/topology",
    );
    expect(screen.getByRole("link", { name: "Monitoring" })).toHaveAttribute(
      "href",
      "/monitoring",
    );
    expect(screen.getByRole("link", { name: "Integrationen" })).toHaveAttribute(
      "href",
      "/integrations",
    );
    expect(screen.getByRole("link", { name: "Audit-Log" })).toHaveAttribute(
      "href",
      "/audit",
    );
    expect(
      screen.getByRole("link", { name: "Einstellungen" }),
    ).toHaveAttribute("href", "/settings");
  });
});
