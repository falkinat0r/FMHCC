/**
 * API-Client (einziger Zugriffspunkt auf das Backend).
 *
 * Semantik (frozen, docs/api-contracts.md):
 * - Cookies via `credentials: "include"` (Session + CSRF-Cookies)
 * - Double-Submit-Header `X-CSRF-Token` fuer state-aendernde Requests
 *   (Wert = hcc_csrf-Cookie; GET/HEAD/OPTIONS ausgenommen)
 * - Error-Envelope wird zentral geparst
 *
 * Typen kommen aus `./types.ts` (generiert aus dem OpenAPI-Snapshot).
 */

export class ApiRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string;

  constructor(status: number, code: string, message: string, requestId: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

interface ErrorBody {
  code: string;
  message: string;
  details: unknown;
  request_id: string;
}

/** Einheitliche Paging-Envelope (frozen Contract). */
export interface Paged<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

/** Liest den Double-Submit-Cookie (hcc_csrf, bewusst nicht HttpOnly). */
export function getCsrfToken(cookieStore: string = document.cookie): string {
  const match = cookieStore.match(/(?:^|;\s*)hcc_csrf=([^;]+)/);
  return match?.[1] ?? "";
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** Baue einen Query-String aus definierten (nicht-null) Paaren. */
export function buildQuery(
  params: Record<string, string | number | null | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s === "" ? "" : `?${s}`;
}

export class ApiClient {
  constructor(readonly baseUrl: string) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const method = (init.method ?? "GET").toUpperCase();
    const headers = new Headers(init.headers);
    if (init.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (!SAFE_METHODS.has(method)) {
      headers.set("X-CSRF-Token", getCsrfToken());
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      method,
      headers,
      credentials: "include",
    });

    if (!response.ok) {
      let code = "unknown";
      let message = `${response.status} ${response.statusText}`;
      let requestId = "";
      try {
        const body = (await response.json()) as { error?: ErrorBody };
        if (body.error) {
          code = body.error.code;
          message = body.error.message;
          requestId = body.error.request_id;
        }
      } catch {
        // nicht-JSON-Fehlerantwort (z. B. Proxy) — Standardwerte behalten
      }
      throw new ApiRequestError(response.status, code, message, requestId);
    }

    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }
}

/** Standard-Client: /api/v1 (Development: Vite-Proxy, Produktion: nginx). */
export const api = new ApiClient("/api/v1");
