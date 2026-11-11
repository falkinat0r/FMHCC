/**
 * TanStack Query Hooks — einziger Datenzugriff der Features.
 *
 * Alle Endpunkte entsprechen dem frozen R0-Vertrag
 * (docs/api-contracts.md §4). Es existiert hier KEIN Endpoint,
 * der nicht im OpenAPI-Snapshot dokumentiert ist.
 *
 * DEV-Modus (isDevFixture): liefert isolierte, klar markierte
 * Fixtures statt Netzwerkzugriffe — nur zur UI-Entwicklung.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api, buildQuery, type Paged } from "./client";
import { isDevFixture } from "./dev";
import {
  FIXTURE_AUDIT,
  FIXTURE_INTEGRATIONS,
  FIXTURE_RESOURCE_DETAILS,
  FIXTURE_RESOURCES,
  FIXTURE_USER,
  FIXTURE_USERS,
  FIXTURE_VERIFY,
  FIXTURE_VERSION,
  pagedFixture,
  type MetricPoint,
  fixtureMetricSeries,
} from "./fixtures";
import type {
  AuditEventOut,
  CurrentUserResponse,
  IntegrationCreate,
  IntegrationOut,
  LoginResponse,
  ResourceDetailOut,
  ResourceOut,
  UserCreate,
  UserOut,
  UserUpdate,
  VerifyResponse,
} from "./types";

const DEFAULT_PAGE_SIZE = 50;
const STALE_TIME = 30_000;
const REFRESH_INTERVAL = 60_000;

/* ------------------------------------------------------------------ */
/* Session / Auth                                                      */
/* ------------------------------------------------------------------ */

function fixtureUser(role: string | null = null): CurrentUserResponse {
  if (role === "viewer" || role === "operator" || role === "admin") {
    return { ...FIXTURE_USER, role, username: `demo-${role}` };
  }
  return FIXTURE_USER;
}

export function useSession() {
  return useQuery({
    queryKey: ["session"],
    queryFn: async (): Promise<CurrentUserResponse> => {
      if (isDevFixture()) {
        const role = new URLSearchParams(window.location.search).get("role");
        return fixtureUser(role);
      }
      return api.get<CurrentUserResponse>("/auth/me");
    },
  });
}

export function useLogin() {
  return useMutation({
    mutationFn: (body: { username: string; password: string }) =>
      api.post<LoginResponse>("/auth/login", body),
  });
}

export function useLogout(onDone?: () => void) {
  return useMutation({
    mutationFn: () => api.post<{ message: string }>("/auth/logout"),
    onSettled: () => onDone?.(),
  });
}

/* ------------------------------------------------------------------ */
/* Version                                                             */
/* ------------------------------------------------------------------ */

export function useVersion() {
  return useQuery({
    queryKey: ["version"],
    queryFn: async () => {
      if (isDevFixture()) return FIXTURE_VERSION;
      return api.get<{ name: string; version: string; release: string; commit: string }>(
        "/version",
      );
    },
    staleTime: 5 * 60_000,
  });
}

/* ------------------------------------------------------------------ */
/* Integrations                                                        */
/* ------------------------------------------------------------------ */

export interface ListParams {
  page?: number;
  pageSize?: number;
}

export function useIntegrations(params: ListParams = {}) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
  return useQuery({
    queryKey: ["integrations", page, pageSize],
    queryFn: async (): Promise<Paged<IntegrationOut>> => {
      if (isDevFixture()) return pagedFixture(FIXTURE_INTEGRATIONS, page, pageSize);
      return api.get<Paged<IntegrationOut>>(
        `/integrations${buildQuery({ page, page_size: pageSize })}`,
      );
    },
    staleTime: STALE_TIME,
    refetchInterval: REFRESH_INTERVAL,
  });
}

export function useIntegration(integrationId: string) {
  return useQuery({
    queryKey: ["integrations", integrationId],
    queryFn: async (): Promise<IntegrationOut> => {
      if (isDevFixture()) {
        const found = FIXTURE_INTEGRATIONS.find(
          (i) => i.integration_id === integrationId,
        );
        if (!found) throw new Error("not_found");
        return found;
      }
      return api.get<IntegrationOut>(`/integrations/${integrationId}`);
    },
    staleTime: STALE_TIME,
  });
}

export function useVerifyIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (integrationId: string) => {
      if (isDevFixture()) return Promise.resolve(FIXTURE_VERIFY);
      return api.post<VerifyResponse>(
        `/integrations/${integrationId}/verify`,
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

export function useUpsertIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      integrationId,
      body,
    }: {
      integrationId: string;
      body: IntegrationCreate;
    }) => {
      if (isDevFixture()) {
        return Promise.resolve({
          id: `fixture-${integrationId}`,
          integration_id: integrationId,
          name: body.name,
          adapter: body.adapter,
          status: "not_configured",
          capabilities: {},
          base_url: body.base_url,
          secret_ref: body.secret_ref,
          last_verified_at: null,
          last_error: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      }
      return api.put<IntegrationOut>(`/integrations/${integrationId}`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

export function useDeleteIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (integrationId: string) =>
      isDevFixture()
        ? Promise.resolve(undefined as unknown)
        : api.delete<void>(`/integrations/${integrationId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });
}

/* ------------------------------------------------------------------ */
/* Resources (Inventar)                                                */
/* ------------------------------------------------------------------ */

export interface ResourceListParams {
  integration?: string | null;
  resourceType?: string | null;
  status?: string | null;
  q?: string | null;
  page?: number;
  pageSize?: number;
}

function filterFixtureResources(params: ResourceListParams): ResourceOut[] {
  let items = FIXTURE_RESOURCES;
  if (params.integration) {
    items = items.filter((r) => r.integration_id === params.integration);
  }
  if (params.resourceType) {
    items = items.filter((r) => r.resource_type === params.resourceType);
  }
  if (params.status) {
    items = items.filter((r) => r.status === params.status);
  }
  if (params.q) {
    const needle = params.q.toLowerCase();
    items = items.filter(
      (r) =>
        (r.name ?? "").toLowerCase().includes(needle) ||
        r.external_id.toLowerCase().includes(needle),
    );
  }
  return items;
}

export function useResources(params: ResourceListParams = {}) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
  const key = ["resources", params.integration ?? "", params.resourceType ?? "", params.status ?? "", params.q ?? "", page, pageSize];
  return useQuery({
    queryKey: key,
    queryFn: async (): Promise<Paged<ResourceOut>> => {
      if (isDevFixture()) {
        return pagedFixture(filterFixtureResources(params), page, pageSize);
      }
      return api.get<Paged<ResourceOut>>(
        `/resources${buildQuery({
          integration: params.integration,
          resource_type: params.resourceType,
          status: params.status,
          q: params.q,
          page,
          page_size: pageSize,
        })}`,
      );
    },
    staleTime: STALE_TIME,
    refetchInterval: REFRESH_INTERVAL,
  });
}

export function useResourceDetail(resourceId: string | null) {
  return useQuery({
    queryKey: ["resource", resourceId ?? ""],
    enabled: resourceId !== null,
    queryFn: async (): Promise<ResourceDetailOut> => {
      if (isDevFixture()) {
        const detail = FIXTURE_RESOURCE_DETAILS[resourceId as string];
        if (!detail) throw new Error("not_found");
        return detail;
      }
      return api.get<ResourceDetailOut>(`/resources/${resourceId}`);
    },
    staleTime: STALE_TIME,
    refetchInterval: REFRESH_INTERVAL,
  });
}

/**
 * Alle Details inkl. Relations — Basis der Topologie.
 * Limitiert (max. `limit`), da das R0-Vertrag Details nur pro
 * Ressource liefert (siehe docs/proposals/frontend-topology-bulk-relations.md).
 */
export function useResourceDetailsAll(limit = 200) {
  const resources = useResources({ page: 1, pageSize: limit });
  return useQuery({
    queryKey: ["resource-details", limit],
    enabled: resources.data !== undefined,
    queryFn: async (): Promise<{
      details: ResourceDetailOut[];
      failed: number;
    }> => {
      const ids = (resources.data?.items ?? []).map((r) => r.id);
      if (isDevFixture()) {
        const found = Object.values(FIXTURE_RESOURCE_DETAILS);
        return { details: found, failed: 0 };
      }
      const settled = await Promise.allSettled(
        ids.map((id) => api.get<ResourceDetailOut>(`/resources/${id}`)),
      );
      const details: ResourceDetailOut[] = [];
      let failed = 0;
      for (const result of settled) {
        if (result.status === "fulfilled") details.push(result.value);
        else failed += 1;
      }
      return { details, failed };
    },
    staleTime: STALE_TIME,
  });
}

/* ------------------------------------------------------------------ */
/* Audit                                                               */
/* ------------------------------------------------------------------ */

export interface AuditParams extends ListParams {
  action?: string | null;
  username?: string | null;
}

export function useAudit(params: AuditParams = {}) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
  return useQuery({
    queryKey: ["audit", params.action ?? "", params.username ?? "", page, pageSize],
    queryFn: async (): Promise<Paged<AuditEventOut>> => {
      if (isDevFixture()) return pagedFixture(FIXTURE_AUDIT, page, pageSize);
      return api.get<Paged<AuditEventOut>>(
        `/audit${buildQuery({
          action: params.action,
          username: params.username,
          page,
          page_size: pageSize,
        })}`,
      );
    },
    staleTime: STALE_TIME,
  });
}

/* ------------------------------------------------------------------ */
/* Users                                                               */
/* ------------------------------------------------------------------ */

export function useUsers(params: ListParams = {}) {
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;
  return useQuery({
    queryKey: ["users", page, pageSize],
    queryFn: async (): Promise<Paged<UserOut>> => {
      if (isDevFixture()) return pagedFixture(FIXTURE_USERS, page, pageSize);
      return api.get<Paged<UserOut>>(
        `/users${buildQuery({ page, page_size: pageSize })}`,
      );
    },
    staleTime: STALE_TIME,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: UserCreate) =>
      isDevFixture()
        ? Promise.resolve({
            id: `fixture-user-${body.username}`,
            username: body.username,
            display_name: body.display_name,
            role: body.role ?? "viewer",
            is_active: true,
            must_change_password: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            last_login_at: null,
          })
        : api.post<UserOut>("/users", body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      userId,
      body,
    }: {
      userId: string;
      body: UserUpdate;
    }) => {
      if (isDevFixture()) {
        return Promise.resolve({
          id: userId,
          username: "demo-user",
          display_name: body.display_name,
          role: body.role ?? "viewer",
          is_active: body.is_active ?? true,
          must_change_password: false,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_login_at: null,
        });
      }
      return api.patch<UserOut>(`/users/${userId}`, body);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

/* ------------------------------------------------------------------ */
/* Monitoring (Metriken)                                               */
/* ------------------------------------------------------------------ */

/**
 * Metrikreihe. Der R0-Vertrag enthaelt KEIN Metrik-Endpoint — die
 * produktiven Aufrufe sind daher "nicht verfuegbar" (keine erfundenen
 * Endpunkte). Im DEV-Modus liefert der Hook klar markierte Fixture-
 * Reihen, damit die Chart-Komponenten getestet werden koennen.
 * Vorschlag: docs/proposals/frontend-metrics-and-alerts.md
 */
export function useMetricSeries(params: {
  resourceId: string | null;
  metric: "cpu" | "memory";
  rangeMinutes: number;
}) {
  const base: UseQueryOptions<{ available: boolean; reason?: string; points: MetricPoint[] }> = {
    queryKey: [
      "metrics",
      params.resourceId ?? "",
      params.metric,
      params.rangeMinutes,
    ],
    staleTime: 60_000,
  };
  return useQuery({
    ...base,
    queryFn: async () => {
      if (isDevFixture()) {
        return {
          available: true,
          points: fixtureMetricSeries(
            params.rangeMinutes,
            params.metric === "cpu" ? 25 : 55,
          ),
        };
      }
      // Kein Metrik-Endpoint im frozen R0-Vertrag.
      return {
        available: false,
        reason:
          "Kein Metrik-Endpunkt im aktuellen API-Vertrag (R0). Siehe docs/proposals/frontend-metrics-and-alerts.md.",
        points: [],
      };
    },
  });
}
