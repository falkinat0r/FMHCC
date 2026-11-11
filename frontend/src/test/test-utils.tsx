/**
 * Test-Helfer (Render-Harness, Fetch-Router, JSON-/Error-Responses).
 */
import type { ReactElement } from "react";
import { render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

/** JSON-Response (Body wird serialisiert, Content-Type gesetzt). */
export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Fehler-Response in der frozen Error-Envelope (docs/api-contracts.md §3). */
export function errorResponse(
  status: number,
  code: string,
  message: string,
  requestId = "test-req",
): Response {
  return jsonResponse(status, {
    error: { code, message, details: null, request_id: requestId },
  });
}

/**
 * Fetch-Stub mit Pfad-Router (Query-Parameter werden ignoriert).
 * - Exakte Pfade: "/auth/me"
 * - Präfix-Pfade für dynamische Segmente: "/resources" antwortet
 *   auch für "/resources/<id>"
 * Unbekannte Pfade liefern 404 (Error-Envelope) — wie ein echtes
 * Backend, damit versehentliche Endpunkt-Erfindungen in Tests fallen.
 */
export function fetchRouter(
  routes: Record<string, Response | ((path: string) => Response)>,
): (input: string | URL | Request) => Promise<Response> {
  return (input) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;
    const path = url.replace(/^\/api\/v1/, "").split("?")[0] ?? "";

    const exact = routes[path];
    if (exact !== undefined) {
      return Promise.resolve(typeof exact === "function" ? exact(path) : exact);
    }
    for (const [key, route] of Object.entries(routes)) {
      if (path.startsWith(`${key}/`)) {
        return Promise.resolve(typeof route === "function" ? route(path) : route);
      }
    }
    return Promise.resolve(
      errorResponse(404, "not_found", `Kein Stub für ${path}`),
    );
  };
}

/** Query-Client ohne Retries — Fehlerzustände sofort sichtbar. */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  });
}

export interface HarnessResult extends RenderResult {
  queryClient: QueryClient;
}

/** Standard-Wrapper: TanStack Query + MemoryRouter (Route injizierbar). */
export function renderWithProviders(
  ui: ReactElement,
  route = "/",
): HarnessResult {
  const queryClient = createTestQueryClient();
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...result, queryClient };
}
