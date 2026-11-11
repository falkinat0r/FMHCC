/**
 * ISOLIERTE TEST-FIXTURES (nur DEV-Modus, `?dev=fixture` /
 * VITE_HCC_DEV_FIXTURE=true).
 *
 * Alle Eintraege sind explizit als Fixture/Demo gekennzeichnet
 * ("demo-"-Prefix, source=manual, Banner in der UI). Sie entsprechen
 * dem frozen R0-Contract (docs/api-contracts.md) und dienen ausschliess-
 * lich der UI-Entwicklung und Demos. Keine echten Namen, keine echten
 * Metadaten der realen Infrastruktur (MASTER_PROMPT §Hardware).
 */
import type {
  AuditEventOut,
  CurrentUserResponse,
  IntegrationOut,
  Paged,
  ResourceDetailOut,
  ResourceOut,
  VerifyResponse,
  UserOut,
  VersionResponse,
} from "./types";

const NOW = "2026-11-10T12:00:00+00:00";
const HOUR_AGO = "2026-11-10T11:00:00+00:00";
const DAY_AGO = "2026-11-09T12:00:00+00:00";

export const FIXTURE_USER: CurrentUserResponse = {
  id: "00000000-0000-4000-8000-000000000001",
  username: "demo-admin",
  display_name: "Demo Admin (Fixture)",
  role: "admin",
  is_active: true,
  must_change_password: false,
  created_at: DAY_AGO,
  last_login_at: HOUR_AGO,
};

export const FIXTURE_VERSION: VersionResponse = {
  name: "hcc-api",
  version: "0.1.0",
  release: "r0-fixture",
  commit: "fixture",
};

export const FIXTURE_INTEGRATIONS: IntegrationOut[] = [
  {
    id: "10000000-0000-4000-8000-000000000001",
    integration_id: "demo-proxmox",
    name: "Demo Proxmox (Fixture)",
    adapter: "proxmox",
    status: "healthy",
    capabilities: {
      nodes: true,
      qemu: true,
      lxc: true,
      storage: true,
      actions: false,
    },
    base_url: "https://proxmox.demo.invalid:8006",
    secret_ref: "HCC_DEMO_PROXMOX_TOKEN",
    last_verified_at: HOUR_AGO,
    last_error: null,
    created_at: DAY_AGO,
    updated_at: HOUR_AGO,
  },
  {
    id: "10000000-0000-4000-8000-000000000002",
    integration_id: "demo-monitoring",
    name: "Demo Monitoring (Fixture)",
    adapter: "monitoring",
    status: "healthy",
    capabilities: { prometheus: true, grafana: false },
    base_url: "https://monitoring.demo.invalid:9090",
    secret_ref: null,
    last_verified_at: HOUR_AGO,
    last_error: null,
    created_at: DAY_AGO,
    updated_at: HOUR_AGO,
  },
  {
    id: "10000000-0000-4000-8000-000000000003",
    integration_id: "demo-pihole",
    name: "Demo Pi-hole (Fixture)",
    adapter: "pihole",
    status: "degraded",
    capabilities: { gravity: true, logs: false },
    base_url: "http://pihole.demo.invalid:8080",
    secret_ref: "HCC_DEMO_PIHOLE_TOKEN",
    last_verified_at: HOUR_AGO,
    last_error: "fixture: simulierter Timeout (keine echte Ursache)",
    created_at: DAY_AGO,
    updated_at: HOUR_AGO,
  },
];

export const FIXTURE_RESOURCES: ResourceOut[] = [
  resource(
    "20000000-0000-4000-8000-000000000101",
    "demo-host-a",
    "host",
    "demo-host-a",
    "healthy",
    { model: "fixture-x86_64", cores: 8, ram_gb: 32, os: "Debian 13 (fixture)" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000102",
    "demo-node-atlas-1",
    "node",
    "demo-node-atlas-1",
    "healthy",
    { proxmox_version: "fixture 8.4", cores: 8, ram_gb: 32 },
  ),
  resource(
    "20000000-0000-4000-8000-000000000103",
    "demo-vm-101",
    "vm",
    "demo-vm-101",
    "healthy",
    { cpu_percent: 12.5, mem_mb: 4096, mem_total_mb: 8192, status: "running" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000104",
    "demo-vm-102",
    "vm",
    "demo-vm-102",
    "degraded",
    { cpu_percent: 88.1, mem_mb: 7900, mem_total_mb: 8192, status: "running" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000105",
    "demo-lxc-201",
    "lxc",
    "demo-lxc-201",
    "healthy",
    { cpu_percent: 3.2, mem_mb: 1024, mem_total_mb: 2048, status: "running" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000201",
    "demo-container-1",
    "container",
    "demo-container-1",
    "down",
    { image: "fixture:latest", state: "exited (137)" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000301",
    "demo-pool-tank",
    "pool",
    "demo-pool-tank",
    "healthy",
    { used_gb: 1200, size_gb: 4000 },
  ),
  resource(
    "20000000-0000-4000-8000-000000000302",
    "demo-dataset-backups",
    "dataset",
    "demo-dataset-backups",
    "degraded",
    { used_gb: 3200, quota_gb: 3500 },
  ),
  resource(
    "20000000-0000-4000-8000-000000000401",
    "demo-tailnet-node",
    "tailnet_node",
    "demo-tailnet-node",
    "healthy",
    { ip: "100.64.0.10 (fixture)" },
  ),
  resource(
    "20000000-0000-4000-8000-000000000501",
    "demo-pihole-stats",
    "dns_stats",
    "demo-pihole-stats",
    "healthy",
    { blocked_today: 1234, queries_total: 45678 },
  ),
];

function resource(
  id: string,
  externalId: string,
  type: ResourceOut["resource_type"],
  name: string,
  status: ResourceOut["status"],
  payload: Record<string, unknown>,
): ResourceOut {
  return {
    id,
    integration_id: externalId.startsWith("demo-lxc") || externalId.startsWith("demo-vm") || externalId.startsWith("demo-node") || externalId.startsWith("demo-host")
      ? "demo-proxmox"
      : externalId.startsWith("demo-container")
        ? "demo-docker"
        : externalId.startsWith("demo-pool") || externalId.startsWith("demo-dataset")
          ? "demo-truenas"
          : externalId.startsWith("demo-tail")
            ? "demo-tailscale"
            : "demo-pihole",
    resource_type: type,
    external_id: externalId,
    name,
    status,
    source: "api",
    payload,
    observed_at: NOW,
    last_seen_at: NOW,
    first_seen_at: DAY_AGO,
  };
}

/** Details (inkl. Relations) — nur Beziehungen aus dem Contract. */
export const FIXTURE_RESOURCE_DETAILS: Record<string, ResourceDetailOut> = {
  "20000000-0000-4000-8000-000000000101": {
    ...FIXTURE_RESOURCES[0]!,
    relations: [
      {
        id: "30000000-0000-4000-8000-000000000001",
        source_resource_id: "20000000-0000-4000-8000-000000000101",
        target_resource_id: "20000000-0000-4000-8000-000000000102",
        relation_type: "runs",
        evidence: "api",
        note: null,
        observed_at: NOW,
        source_name: "demo-host-a",
        target_name: "demo-node-atlas-1",
      },
    ],
  },
  "20000000-0000-4000-8000-000000000102": {
    ...FIXTURE_RESOURCES[1]!,
    relations: [
      relation(
        "30000000-0000-4000-8000-000000000002",
        "20000000-0000-4000-8000-000000000102",
        "20000000-0000-4000-8000-000000000103",
        "contains",
        "api",
        "demo-node-atlas-1",
        "demo-vm-101",
      ),
      relation(
        "30000000-0000-4000-8000-000000000003",
        "20000000-0000-4000-8000-000000000102",
        "20000000-0000-4000-8000-000000000104",
        "contains",
        "api",
        "demo-node-atlas-1",
        "demo-vm-102",
      ),
      relation(
        "30000000-0000-4000-8000-000000000004",
        "20000000-0000-4000-8000-000000000102",
        "20000000-0000-4000-8000-000000000105",
        "contains",
        "api",
        "demo-node-atlas-1",
        "demo-lxc-201",
      ),
    ],
  },
  "20000000-0000-4000-8000-000000000103": {
    ...FIXTURE_RESOURCES[2]!,
    relations: [
      relation(
        "30000000-0000-4000-8000-000000000005",
        "20000000-0000-4000-8000-000000000103",
        "20000000-0000-4000-8000-000000000401",
        "network",
        "inferred",
        "demo-vm-101",
        "demo-tailnet-node",
      ),
    ],
  },
  "20000000-0000-4000-8000-000000000104": {
    ...FIXTURE_RESOURCES[3]!,
    relations: [],
  },
  "20000000-0000-4000-8000-000000000105": {
    ...FIXTURE_RESOURCES[4]!,
    relations: [],
  },
  "20000000-0000-4000-8000-000000000201": {
    ...FIXTURE_RESOURCES[5]!,
    relations: [
      relation(
        "30000000-0000-4000-8000-000000000006",
        "20000000-0000-4000-8000-000000000101",
        "20000000-0000-4000-8000-000000000201",
        "runs",
        "manual",
        "demo-host-a",
        "demo-container-1",
      ),
    ],
  },
  "20000000-0000-4000-8000-000000000301": {
    ...FIXTURE_RESOURCES[6]!,
    relations: [
      relation(
        "30000000-0000-4000-8000-000000000007",
        "20000000-0000-4000-8000-000000000101",
        "20000000-0000-4000-8000-000000000301",
        "storage_on",
        "manual",
        "demo-host-a",
        "demo-pool-tank",
      ),
    ],
  },
  "20000000-0000-4000-8000-000000000302": {
    ...FIXTURE_RESOURCES[7]!,
    relations: [
      relation(
        "30000000-0000-4000-8000-000000000008",
        "20000000-0000-4000-8000-000000000301",
        "20000000-0000-4000-8000-000000000302",
        "contains",
        "api",
        "demo-pool-tank",
        "demo-dataset-backups",
      ),
    ],
  },
  "20000000-0000-4000-8000-000000000401": {
    ...FIXTURE_RESOURCES[8]!,
    relations: [],
  },
  "20000000-0000-4000-8000-000000000501": {
    ...FIXTURE_RESOURCES[9]!,
    relations: [],
  },
};

function relation(
  id: string,
  sourceId: string,
  targetId: string,
  relationType: string,
  evidence: "api" | "manual" | "inferred",
  sourceName: string,
  targetName: string,
) {
  return {
    id,
    source_resource_id: sourceId,
    target_resource_id: targetId,
    relation_type: relationType,
    evidence,
    note: evidence === "manual" ? "manuell gepflegt (fixture)" : null,
    observed_at: NOW,
    source_name: sourceName,
    target_name: targetName,
  };
}

export const FIXTURE_USERS: UserOut[] = [
  {
    id: FIXTURE_USER.id,
    username: "demo-admin",
    display_name: "Demo Admin (Fixture)",
    role: "admin",
    is_active: true,
    must_change_password: false,
    created_at: DAY_AGO,
    updated_at: HOUR_AGO,
    last_login_at: HOUR_AGO,
  },
  {
    id: "00000000-0000-4000-8000-000000000002",
    username: "demo-operator",
    display_name: "Demo Operator (Fixture)",
    role: "operator",
    is_active: true,
    must_change_password: false,
    created_at: DAY_AGO,
    updated_at: DAY_AGO,
    last_login_at: null,
  },
  {
    id: "00000000-0000-4000-8000-000000000003",
    username: "demo-viewer",
    display_name: "Demo Viewer (Fixture)",
    role: "viewer",
    is_active: false,
    must_change_password: true,
    created_at: DAY_AGO,
    updated_at: HOUR_AGO,
    last_login_at: DAY_AGO,
  },
];

export const FIXTURE_AUDIT: AuditEventOut[] = [
  {
    id: 1,
    username: "demo-admin",
    action: "auth.login",
    resource_type: null,
    resource_id: null,
    ip_address: "10.0.0.5 (fixture)",
    user_agent: "hcc-ui (fixture)",
    details: { outcome: "ok" },
    created_at: HOUR_AGO,
  },
  {
    id: 2,
    username: "demo-admin",
    action: "integrations.verify",
    resource_type: "integration",
    resource_id: "demo-proxmox",
    ip_address: "10.0.0.5 (fixture)",
    user_agent: "hcc-ui (fixture)",
    details: { status: "ok" },
    created_at: HOUR_AGO,
  },
  {
    id: 3,
    username: "demo-operator",
    action: "auth.login",
    resource_type: null,
    resource_id: null,
    ip_address: "10.0.0.6 (fixture)",
    user_agent: "hcc-ui (fixture)",
    details: { outcome: "ok" },
    created_at: DAY_AGO,
  },
];

export const FIXTURE_VERIFY: VerifyResponse = {
  integration_id: "demo-proxmox",
  status: "ok",
  message: "Fixture: simulierter OK-Verbindungscheck",
  capabilities: { nodes: true, qemu: true, lxc: true, storage: true },
  api_version: "fixture 8.4",
  checked_at: NOW,
};

/**
 * Fixture-Metrikreihe (deterministisch, nur DEV-Modus).
 * `points` Zeitpunkte, Basiswert + sinusfoermige Variation.
 */
export interface MetricPoint {
  readonly ts: string;
  readonly value: number;
}

export function fixtureMetricSeries(
  rangeMinutes: number,
  base: number,
  points = 24,
): MetricPoint[] {
  const stepMs = (rangeMinutes * 60_000) / points;
  const end = new Date(NOW).getTime();
  const result: MetricPoint[] = [];
  for (let i = 0; i < points; i += 1) {
    const t = end - (points - 1 - i) * stepMs;
    const wave = Math.sin(i / 3.1) * 12;
    const drift = ((i * 7) % 10) - 5;
    result.push({
      ts: new Date(t).toISOString(),
      value: Math.max(0, Math.round((base + wave + drift) * 10) / 10),
    });
  }
  return result;
}

export function pagedFixture<T>(items: T[], page = 1, pageSize = 50): Paged<T> {
  const total = items.length;
  const total_pages = Math.max(1, Math.ceil(total / pageSize));
  const safePage = Math.min(Math.max(1, page), total_pages);
  const start = (safePage - 1) * pageSize;
  return {
    items: items.slice(start, start + pageSize),
    page: safePage,
    page_size: pageSize,
    total,
    total_pages,
  };
}
