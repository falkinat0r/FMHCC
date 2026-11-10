import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useLocation } from "react-router-dom";

import { AuthProvider, useAuth } from "./AuthProvider";
import { RequireAuth } from "./RequireAuth";
import { FIXTURE_USER } from "../../api/fixtures";
import type { Role } from "../../api/types";
import {
  createTestQueryClient,
  errorResponse,
  fetchRouter,
  jsonResponse,
} from "../../test/test-utils";

function AuthProbe() {
  const { status, user } = useAuth();
  return (
    <p data-testid="auth-probe">
      {status}:{user?.username ?? "none"}
    </p>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location-probe">{location.pathname}</p>;
}

function renderAuth(probe: ReactNode) {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <AuthProvider>{probe}</AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubSession(role: Role) {
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
}

describe("AuthProvider", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("beginnt im Ladezustand (Session wird geprüft)", async () => {
    vi.stubGlobal(
      "fetch",
      () => new Promise<Response>(() => {}), // pendet bewusst
    );
    renderAuth(<AuthProbe />);
    expect(screen.getByTestId("auth-probe")).toHaveTextContent("loading:");
  });

  it("ist 'user', wenn /auth/me eine Session liefert", async () => {
    stubSession("operator");
    renderAuth(<AuthProbe />);
    await screen.findByText("user:demo-operator");
  });

  it("ist 'guest' bei 401 (keine Session) — kein erfundener Benutzer", async () => {
    vi.stubGlobal(
      "fetch",
      fetchRouter({
        "/auth/me": errorResponse(401, "unauthorized", "Nicht authentifiziert"),
      }),
    );
    renderAuth(<AuthProbe />);
    await screen.findByText("guest:none");
  });

  it("wirft außerhalb des Providers eine klare Fehlermeldung", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const queryClient = createTestQueryClient();
    expect(() =>
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <AuthProbe />
          </MemoryRouter>
        </QueryClientProvider>,
      ),
    ).toThrow(/AuthProvider/);
    spy.mockRestore();
  });
});

describe("RequireAuth", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("leitet ohne Session zu /login um (mit Return-URL)", async () => {
    vi.stubGlobal(
      "fetch",
      fetchRouter({
        "/auth/me": errorResponse(401, "unauthorized", "Nicht authentifiziert"),
      }),
    );
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={["/compute"]}>
          <AuthProvider>
            <RequireAuth>
              <p>GEHEIMER_BEREICH</p>
            </RequireAuth>
            <LocationProbe />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByText("/login");
    expect(screen.queryByText("GEHEIMER_BEREICH")).not.toBeInTheDocument();
  });

  it("zeigt den Inhalt mit gültiger Session", async () => {
    stubSession("admin");
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={["/"]}>
          <AuthProvider>
            <RequireAuth>
              <p>GEHEIMER_BEREICH</p>
            </RequireAuth>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("GEHEIMER_BEREICH")).toBeInTheDocument();
  });
});
