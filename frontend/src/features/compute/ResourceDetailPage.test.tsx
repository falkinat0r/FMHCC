import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import ResourceDetailPage from "./ResourceDetailPage";
import { AuthProvider } from "../auth/AuthProvider";
import {
  FIXTURE_RESOURCE_DETAILS,
  FIXTURE_USER,
} from "../../api/fixtures";
import type { Role } from "../../api/types";
import {
  createTestQueryClient,
  fetchRouter,
  jsonResponse,
} from "../../test/test-utils";

const VM_ID = "20000000-0000-4000-8000-000000000103"; // demo-vm-101

function renderDetailForRole(role: Role) {
  vi.stubGlobal(
    "fetch",
    fetchRouter({
      "/auth/me": jsonResponse(200, {
        ...FIXTURE_USER,
        role,
        username: `demo-${role}`,
      }),
      "/resources": jsonResponse(200, FIXTURE_RESOURCE_DETAILS[VM_ID]!),
    }),
  );
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/resources/${VM_ID}`]}>
        <AuthProvider>
          <Routes>
            <Route path="/resources/:resourceId" element={<ResourceDetailPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ResourceDetailPage (VM)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lädt Detaildaten aus GET /resources/{id}", async () => {
    renderDetailForRole("operator");
    await screen.findByRole("heading", { name: /demo-vm-101/ });
    // Integration wird aus dem Detail-Contract gezeigt
    expect(screen.getByText(/Integration: demo-proxmox/)).toBeInTheDocument();
  });

  it("zeigt operator die Aktionsknöpfe (Start/Shutdown/Reboot)", async () => {
    renderDetailForRole("operator");
    await screen.findByRole("heading", { name: /demo-vm-101/ });

    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Shutdown" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reboot" })).toBeInTheDocument();
  });

  it("zeigt viewer keinen Aktionsknopf, sondern den RBAC-Hinweis", async () => {
    renderDetailForRole("viewer");
    await screen.findByRole("heading", { name: /demo-vm-101/ });

    expect(screen.queryByRole("button", { name: "Start" })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Verwaltungsaktionen erfordern die Rolle operator/),
    ).toBeInTheDocument();
  });

  it("blockiert die Aktion im Dialog, weil der R0-Vertrag keinen Endpunkt kennt", async () => {
    renderDetailForRole("admin");
    await screen.findByRole("heading", { name: /demo-vm-101/ });

    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Aktion derzeit nicht verfügbar");
    expect(dialog).toHaveTextContent(/frontend-vm-actions\.md/);
    // Es darf keine Ausführung ohne Endpunkt möglich sein:
    expect(
      screen.queryByRole("button", { name: "Starten bestätigen" }),
    ).not.toBeInTheDocument();
  });
});
