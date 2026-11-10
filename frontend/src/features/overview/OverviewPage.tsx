import { useMemo, type ReactNode } from "react";
import {
  AlertTriangle,
  Boxes,
  Cpu,
  HardDrive,
  MonitorCog,
  Server,
} from "lucide-react";

import {
  useAudit,
  useIntegrations,
  useResources,
} from "../../api/query";
import type { ResourceOut } from "../../api/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";
import { Skeleton } from "../../components/ui/skeleton";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { formatCount, timeAgo } from "../../lib/format";
import { cn } from "../../lib/cn";
import { useAuth } from "../auth/AuthProvider";
import { canAdmin } from "../../lib/permissions";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";

/**
 * Dashboard (Overview).
 *
 * Alle Werte kommen aus den echten v1-Endpoints (R0-Vertrag):
 * GET /resources, GET /integrations, GET /audit.
 * Fehlende Funktionen (Alerts, Metriken) werden explizit als
 * "nicht verfuegbar" angezeigt — nie als erfundene Daten.
 */
export default function OverviewPage() {
  const resources = useResources({ page: 1, pageSize: 200 });
  const integrations = useIntegrations();
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const audit = useAudit({
    page: 1,
    pageSize: 8,
  });

  const stats = useMemo(() => summarizeResources(resources.data?.items ?? []), [
    resources.data,
  ]);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Dashboard</h1>
        <p className="text-xs text-muted-foreground">
          Übersicht über Hosts, Compute, Storage, Integrationen und Ereignisse
          {resources.data !== undefined &&
            resources.data.items.length < resources.data.total && (
              <span>
                {" "}
                (Ansicht zeigt die letzten {resources.data.items.length} von{" "}
                {resources.data.total} Ressourcen)
              </span>
            )}
        </p>
      </div>

      <KpiRow
        loading={resources.isLoading}
        error={resources.error}
        retry={() => void resources.refetch()}
        stats={stats}
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <IntegrationHealthPanel
          query={integrations}
        />
        <RecentEventsPanel isAdmin={isAdmin} query={audit} />
      </div>

      <AlertsPanel />
    </div>
  );
}

/* ------------------------------------------------------------------ */

interface ResourceStats {
  hosts: number;
  vms: number;
  lxcs: number;
  containers: number;
  storage: number;
  hostsDown: number;
  vmsDown: number;
  lxcsDown: number;
  containersDown: number;
  lastObserved: string | null;
}

function summarizeResources(items: ResourceOut[]): ResourceStats {
  const stats: ResourceStats = {
    hosts: 0,
    vms: 0,
    lxcs: 0,
    containers: 0,
    storage: 0,
    hostsDown: 0,
    vmsDown: 0,
    lxcsDown: 0,
    containersDown: 0,
    lastObserved: null,
  };
  for (const item of items) {
    switch (item.resource_type) {
      case "host":
        stats.hosts += 1;
        if (item.status === "down") stats.hostsDown += 1;
        break;
      case "vm":
        stats.vms += 1;
        if (item.status === "down") stats.vmsDown += 1;
        break;
      case "lxc":
        stats.lxcs += 1;
        if (item.status === "down") stats.lxcsDown += 1;
        break;
      case "container":
        stats.containers += 1;
        if (item.status === "down") stats.containersDown += 1;
        break;
      case "pool":
      case "dataset":
        stats.storage += 1;
        break;
      default:
        break;
    }
    const observed = item.observed_at ?? item.last_seen_at ?? null;
    if (observed !== null && (stats.lastObserved === null || observed > stats.lastObserved)) {
      stats.lastObserved = observed;
    }
  }
  return stats;
}

function KpiRow({
  loading,
  error,
  retry,
  stats,
}: {
  loading: boolean;
  error: unknown;
  retry: () => void;
  stats: ResourceStats;
}) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <Card key={i}>
            <CardContent className="p-3">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="mt-2 h-7 w-10" />
              <Skeleton className="mt-2 h-3 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }
  if (error !== null) {
    return (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Card className="md:col-span-2 xl:col-span-3">
          <CardContent className="p-3">
            {queryStatePanel(error, retry)}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <KpiCard
        icon={Server}
        title="Hosts"
        value={formatCount(stats.hosts)}
        sub={
          stats.hostsDown > 0
            ? `${formatCount(stats.hostsDown)} down`
            : "alle erreichbar"
        }
        subClass={stats.hostsDown > 0 ? "text-status-down" : "text-status-healthy"}
      />
      <KpiCard
        icon={MonitorCog}
        title="VMs"
        value={formatCount(stats.vms)}
        sub={
          stats.vmsDown > 0 ? `${formatCount(stats.vmsDown)} down` : "keine down"
        }
        subClass={stats.vmsDown > 0 ? "text-status-down" : "text-status-healthy"}
      />
      <KpiCard
        icon={Boxes}
        title="LXC"
        value={formatCount(stats.lxcs)}
        sub={
          stats.lxcsDown > 0
            ? `${formatCount(stats.lxcsDown)} down`
            : "keine down"
        }
        subClass={stats.lxcsDown > 0 ? "text-status-down" : "text-status-healthy"}
      />
      <KpiCard
        icon={Cpu}
        title="Container"
        value={formatCount(stats.containers)}
        sub={
          stats.containersDown > 0
            ? `${formatCount(stats.containersDown)} down`
            : "keine down"
        }
        subClass={
          stats.containersDown > 0 ? "text-status-down" : "text-status-healthy"
        }
      />
      <KpiCard
        icon={HardDrive}
        title="Storage"
        value={formatCount(stats.storage)}
        sub="Pools + Datasets"
        subClass="text-muted-foreground"
      />
      <KpiCard
        icon={AlertTriangle}
        title="Letzte Daten"
        value={
          stats.lastObserved === null ? "n/v" : timeAgo(stats.lastObserved)
        }
        sub="observed_at der Ressourcen"
        subClass="text-muted-foreground"
      />
    </div>
  );
}

function KpiCard({
  icon: Icon,
  title,
  value,
  sub,
  subClass,
}: {
  icon: typeof Server;
  title: string;
  value: string;
  sub: string;
  subClass?: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 p-3">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="text-[11px] font-medium uppercase tracking-wide">
            {title}
          </span>
        </div>
        <span className="text-xl font-semibold leading-none">{value}</span>
        <span className={cn("text-[11px]", subClass)}>{sub}</span>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

type IntegrationsQuery = ReturnType<typeof useIntegrations>;

function IntegrationHealthPanel({ query }: { query: IntegrationsQuery }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Service-Health (Integrationen)</CardTitle>
        <CardDescription>
          Verbindungsstatus der konfigurierten Anbindungen
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.isLoading && (
          <div className="flex flex-col gap-2" aria-busy="true">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        )}
        {query.error !== null &&
          queryStatePanel(query.error, () => void query.refetch())}
        {query.data !== undefined &&
          query.data.items.length === 0 &&
          <StatePanel
            state="empty"
            emptyText="Noch keine Integrationen konfiguriert."
          />}
        {query.data !== undefined && query.data.items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Integration</TableHead>
                <TableHead>Adapter</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Letzte Prüfung</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>
                    <span className="font-medium">{item.name}</span>
                    <span className="block text-[10px] text-muted-foreground">
                      {item.integration_id}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {item.adapter}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={item.status} />
                    {item.last_error !== null && (
                      <span className="mt-1 block max-w-48 truncate text-[10px] text-status-down" title={item.last_error}>
                        {item.last_error}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {timeAgo(item.last_verified_at)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

type AuditQuery = ReturnType<typeof useAudit>;

function RecentEventsPanel({
  isAdmin,
  query,
}: {
  isAdmin: boolean;
  query: AuditQuery;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Letzte Ereignisse</CardTitle>
        <CardDescription>
          {isAdmin
            ? "Audit-Log (append-only)"
            : "Nicht verfügbar — Audit-Log benötigt die Rolle admin (RBAC)."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!isAdmin ? (
          <StatePanel
            state="not_configured"
            notConfiguredText="Audit-Log ist nur für die Rolle admin lesbar (serverseitige RBAC-Prüfung)."
          />
        ) : query.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true">
            {Array.from({ length: 4 }, (_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : query.error !== null ? (
          queryStatePanel(query.error, () => void query.refetch())
        ) : query.data !== undefined && query.data.items.length === 0 ? (
          <StatePanel state="empty" emptyText="Keine Audit-Events vorhanden." />
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {(query.data?.items ?? []).map((event) => (
              <li key={event.id} className="flex items-start justify-between gap-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">
                    {event.action}
                  </p>
                  <p className="truncate text-[11px] text-muted-foreground">
                    {event.username ?? "unbekannt"}
                    {event.resource_type !== null &&
                      ` · ${event.resource_type}/${event.resource_id ?? "?"}`}
                  </p>
                </div>
                <span className="shrink-0 text-[11px] text-muted-foreground">
                  {timeAgo(event.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------------ */

function AlertsPanel(): ReactNode {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Alerts</CardTitle>
      </CardHeader>
      <CardContent>
        <StatePanel
          state="not_configured"
          notConfiguredText={
            <>
              <span className="mb-2 flex items-center gap-2">
                <AlertTriangle
                  className="h-4 w-4 text-status-degraded"
                  aria-hidden="true"
                />
                Keine Alert-Quelle im aktuellen API-Vertrag (R0)
              </span>
              <span>
                Das R0-Vertrag-Verzeichnis enthält keinen Alert-Endpunkt.
                Alerting folgt über die bestehende Monitoring-Anbindung
                (Prometheus) — Contract-Änderungsvorschlag:{" "}
                <span className="font-mono">
                  docs/proposals/frontend-metrics-and-alerts.md
                </span>
                .
              </span>
            </>
          }
        />
      </CardContent>
    </Card>
  );
}
