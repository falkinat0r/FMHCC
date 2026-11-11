import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";

import {
  useAudit,
  useIntegrations,
  useMetricSeries,
  useResources,
} from "../../api/query";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { MetricChart } from "../../components/common/MetricChart";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Select } from "../../components/ui/select";
import { Label } from "../../components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { timeAgo } from "../../lib/format";
import { isDevFixture } from "../../api/dev";
import { useAuth } from "../auth/AuthProvider";
import { canAdmin } from "../../lib/permissions";

const RANGES = [
  { label: "1 h", minutes: 60 },
  { label: "6 h", minutes: 6 * 60 },
  { label: "24 h", minutes: 24 * 60 },
  { label: "7 d", minutes: 7 * 24 * 60 },
  { label: "30 d", minutes: 30 * 24 * 60 },
] as const;

/**
 * Monitoring-Oberfläche (R3-Förderung, R0-Vertrag als Grundlage):
 * - Quellen: Integrationen des Adapter-Typs "monitoring"
 *   (Prometheus/Grafana) — nur vorhandene Endpunkte.
 * - Metriken: CPU/RAM-Charts mit Historie 1h…30d. IM R0-VERTRAG
 *   GIBT ES KEIN METRIK-ENDPOINT — die Ansicht zeigt das explizit
 *   als "nicht verfuegbar" an (keine Mock-Charts in Produktion).
 * - Ereignisse: Audit-Log (admin, RBAC).
 * - Alerts: kein Endpunkt im Vertrag — als nicht verfuegbar gezeigt.
 */
export default function MonitoringPage() {
  const integrations = useIntegrations();
  const resources = useResources({ page: 1, pageSize: 200 });
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const audit = useAudit({ page: 1, pageSize: 20 });

  const [resourceId, setResourceId] = useState("");
  const [rangeMinutes, setRangeMinutes] = useState<number>(24 * 60);
  const [metric, setMetric] = useState<"cpu" | "memory">("cpu");

  const monitoringIntegrations = useMemo(
    () => (integrations.data?.items ?? []).filter((i) => i.adapter === "monitoring"),
    [integrations.data],
  );

  const metricQuery = useMetricSeries({
    resourceId: resourceId === "" ? null : resourceId,
    metric,
    rangeMinutes,
  });

  const resourceOptions = useMemo(
    () => (resources.data?.items ?? []).filter((r) =>
      ["vm", "lxc", "container", "host", "node"].includes(r.resource_type),
    ),
    [resources.data],
  );

  return (
    <div>
      <PageHeader
        title="Monitoring"
        description="Metriken, Ereignisse und Alerts aus vorhandenen Quellen. Fehlende Quellen werden nicht simuliert."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quellen (Monitoring-Integrationen)</CardTitle>
            <CardDescription>
              Konfigurierte Prometheus-/Grafana-Instanzen (Adapter "monitoring")
            </CardDescription>
          </CardHeader>
          <CardContent>
            {integrations.isLoading && <StatePanel state="loading" rows={2} />}
            {integrations.error !== null &&
              queryStatePanel(integrations.error, () => void integrations.refetch())}
            {integrations.data !== undefined && monitoringIntegrations.length === 0 && (
              <StatePanel
                state="empty"
                emptyText="Keine Monitoring-Integration (Prometheus/Grafana) konfiguriert."
              />
            )}
            {monitoringIntegrations.length > 0 && (
              <ul className="flex flex-col gap-2">
                {monitoringIntegrations.map((item) => (
                  <li
                    key={item.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-border p-2"
                  >
                    <div>
                      <p className="text-xs font-medium">{item.name}</p>
                      <p className="text-[10px] text-muted-foreground">
                        {item.base_url ?? "n/v"} · letzte Prüfung{" "}
                        {timeAgo(item.last_verified_at)}
                      </p>
                    </div>
                    <StatusBadge status={item.status} />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Alerts</CardTitle>
            <CardDescription>
              Regelbasierte Alerts ueber die bestehende Monitoring-Anbindung
            </CardDescription>
          </CardHeader>
          <CardContent>
            <StatePanel
              state="not_configured"
              notConfiguredText={
                <>
                  <span className="mb-1 flex items-center gap-2">
                    <AlertTriangle
                      className="h-4 w-4 text-status-degraded"
                      aria-hidden="true"
                    />
                    Keine Alert-Endpunkte im R0-Vertrag
                  </span>
                  <span>
                    Alerting folgt ueber Prometheus — Contract-Vorschlag:{" "}
                    <span className="font-mono">
                      docs/proposals/frontend-metrics-and-alerts.md
                    </span>
                  </span>
                </>
              }
            />
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Metriken (CPU / RAM)</CardTitle>
            <CardDescription>
              Historische Zeiträume · Quellkennzeichnung
              {isDevFixture() && (
                <span className="ml-1 text-status-degraded">· DEV-FIXTURE</span>
              )}
            </CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="metric-resource">Ressource</Label>
              <Select
                id="metric-resource"
                className="w-52"
                value={resourceId}
                onChange={(e) => setResourceId(e.target.value)}
              >
                <option value="">— wählen —</option>
                {resourceOptions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name ?? r.external_id} ({r.resource_type})
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="metric-kind">Metrik</Label>
              <Select
                id="metric-kind"
                className="w-32"
                value={metric}
                onChange={(e) => setMetric(e.target.value as "cpu" | "memory")}
              >
                <option value="cpu">CPU</option>
                <option value="memory">RAM</option>
              </Select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="metric-range">Zeitraum</Label>
              <div className="flex gap-1" role="group" aria-label="Zeitraum">
                {RANGES.map((range) => (
                  <Button
                    key={range.label}
                    size="sm"
                    variant={
                      range.minutes === rangeMinutes ? "default" : "ghost"
                    }
                    aria-pressed={range.minutes === rangeMinutes}
                    onClick={() => setRangeMinutes(range.minutes)}
                  >
                    {range.label}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {metricQuery.isLoading && <StatePanel state="loading" rows={3} />}
          {metricQuery.error !== null &&
            queryStatePanel(metricQuery.error, () => void metricQuery.refetch())}
          {metricQuery.data !== undefined &&
            metricQuery.data.available === false && (
              <StatePanel
                state="not_configured"
                notConfiguredText={
                  metricQuery.data.reason ??
                  "Keine Metrik-Datenquelle konfiguriert."
                }
              />
            )}
          {metricQuery.data !== undefined &&
            metricQuery.data.available === true &&
            (resourceId === "" ? (
              <StatePanel
                state="empty"
                emptyText="Ressource auswählen, um die Metrik zu sehen."
              />
            ) : (
              <MetricChart
                label={metric === "cpu" ? "CPU-Auslastung" : "RAM-Auslastung"}
                points={metricQuery.data.points}
                unit="%"
                color={metric === "cpu" ? "#35b5a2" : "#818cf8"}
              />
            ))}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Ereignisse</CardTitle>
          <CardDescription>
            {isAdmin
              ? "Audit-Events (append-only)"
              : "Nicht verfügbar — Audit-Log erfordert die Rolle admin (RBAC)."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!isAdmin ? (
            <StatePanel
              state="not_configured"
              notConfiguredText="Ereignisliste nur für admin (serverseitige RBAC-Prüfung)."
            />
          ) : audit.isLoading ? (
            <StatePanel state="loading" rows={4} />
          ) : audit.error !== null ? (
            queryStatePanel(audit.error, () => void audit.refetch())
          ) : audit.data !== undefined && audit.data.items.length === 0 ? (
            <StatePanel state="empty" emptyText="Keine Ereignisse vorhanden." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Zeit (UTC)</TableHead>
                  <TableHead>Aktion</TableHead>
                  <TableHead>Benutzer</TableHead>
                  <TableHead>Ressource</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(audit.data?.items ?? []).map((event) => (
                  <TableRow key={event.id}>
                    <TableCell className="whitespace-nowrap text-xs">
                      {timeAgo(event.created_at)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{event.action}</TableCell>
                    <TableCell className="text-xs">{event.username ?? "—"}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {event.resource_type !== null
                        ? `${event.resource_type}/${event.resource_id ?? "?"}`
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
