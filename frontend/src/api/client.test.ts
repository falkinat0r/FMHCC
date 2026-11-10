import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiRequestError, getCsrfToken } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("getCsrfToken", () => {
  it("liest den hcc_csrf-Cookie aus dem Cookie-Store", () => {
    expect(getCsrfToken("a=b; hcc_csrf=token123; c=d")).toBe("token123");
  });

  it("liefert leere Zeichenkette ohne CSRF-Cookie", () => {
    expect(getCsrfToken("a=b")).toBe("");
  });
});

describe("ApiClient (R0-Shell)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("setzt X-CSRF-Token bei POST (Double-Submit)", async () => {
    document.cookie = "hcc_csrf=testtoken; path=/";
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("/api/v1");
    await client.post("/auth/logout");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/logout");
    expect(new Headers(init.headers).get("x-csrf-token")).toBe("testtoken");
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
  });

  it("setzt X-CSRF-Token nicht bei GET", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(200, { items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("/api/v1");
    await client.get("/integrations");

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("x-csrf-token")).toBeNull();
  });

  it("wirft ApiRequestError mit Error-Envelope-Feldern", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      jsonResponse(403, {
        error: {
          code: "forbidden",
          message: "CSRF-Pruefung fehlgeschlagen",
          details: null,
          request_id: "req-0001",
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("/api/v1");
    await expect(client.post("/auth/logout")).rejects.toMatchObject({
      status: 403,
      code: "forbidden",
      message: "CSRF-Pruefung fehlgeschlagen",
      requestId: "req-0001",
    });
  });

  it("ist eine ApiRequestError-Instanz", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(500, {}));
    vi.stubGlobal("fetch", fetchMock);

    const client = new ApiClient("/api/v1");
    const error = await client.get("/definitiv-nicht-da").catch((err: unknown) => err);
    expect(error).toBeInstanceOf(ApiRequestError);
  });
});
