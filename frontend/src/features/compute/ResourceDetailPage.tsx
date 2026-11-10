import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useMetricSeries, useResourceDetail } from "../../api/query";
import { useAuth } from "../auth/AuthProvider";
import { canOperate } from "../../lib/permissions";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { JsonView } from "../../components/common/JsonView";
import { MetricChart } from "../../components/common/MetricChart";
import { ActionDialog, type ComputeAction } from "./ActionDialog";
import { ArrowLeft, Power, RefreshCw, Square } from "lucide-react";
import { formatDateTime, timeAgo } from "../../lib/format";
import { sourceMeta } from "../../lib/status";
import { isDevFixture } from "../../api/dev";

/**
 * Ressourcendetails (GET /api/v1/resources/{id}):
 * Identitaet, Status, Payload, Beziehungen (mit Evidenz) und —
 * soweit ein Endpunkt existiert — Metriken. VM/LXC erhalten
 * rollenabhaengige Aktionsknopfe (R0: blockiert, siehe Proposal).
 */
export default function ResourceDetailPage() {
  const { resourceId } = useParams<{ resourceId: string }>();
  const detail = useResourceDetail(resourceId ?? null);
  const { user } = useAuth();
  const operator = canOperate(user?.role);

  const [action, setAction] = useState<ComputeAction | null>(null);
  const [rangeMinutes, setRangeMinutes] = useState(24 * 60);

  // Hooks strikt vor den early returns (Rules of Hooks):
  const metric = useMetricSeries({
    resourceId: detail.data?.id ?? null,
    metric: "cpu",
    rangeMinutes,
  });
  const metricMem = useMetricSeries({
    resourceId: detail.data?.id ?? null,
    metric: "memory",
    rangeMinutes,
  });

  if (detail.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <StatePanel state="loading" rows={8} />
      </div>
    );
  }

  if (detail.error !== null || detail.data === undefined) {
    return (
      <div className="flex flex-col gap-3">
        <Link to="/compute" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Zurueck zu Compute
        </Link>
        {queryStatePanel(detail.error ?? new Error("Ressource nicht gefunden"), () =>
          void detail.refetch(),
        )}
      </div>
    );
  }

  const item = detail.data;
  const isActionable = item.resource_type === "vm" || item.resource_type === "lxc";

  const ranges = [
    { label: "1 h", minutes: 60 },
    { label: "6 h", minutes: 6 * 60 },
    { label: "24 h", minutes: 24 * 60 },
    { label: "7 d", minutes: 7 * 24 * 60 },
    { label: "30 d", minutes: 30 * 24 * 60 },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            to="/compute"
            aria-label="Zurueck zu Compute"
            className="rounded-md border border-border p-1.5 hover:bg-accent"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <div>
            <h1 className="flex items-center gap-2 text-lg font-semibold">
              {item.name ?? item.external_id}
              <StatusBadge status={item.status} />
            </h1>
            <p className="text-xs text-muted-foreground">
              <span className="font-mono">{item.external_id}</span>
              {" · "}
              {item.resource_type}
              {" · "}
              Integration: {item.integration_id}
              {" · "}
              Quelle: {sourceMeta(item.source).label}
            </p>
          </div>
        </div>

        {isActionable && (
          <div className="flex flex-wrap items-center gap-2">
            {operator ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setAction("start")}
                >
                  <Power className="h-3.5 w-3.5" aria-hidden="true" />
                  Start
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setAction("stop")}
                >
                  <Square className="h-3.5 w-3.5" aria-hidden="true" />
                  Shutdown
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setAction("reboot")}
                >
                  <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
                  Reboot
                </Button>
              </>
            ) : (
              <p className="text-xs text-muted-foreground">
                Verwaltungsaktionen erfordern die Rolle operator (RBAC,
                serverseitig geprüft).
              </p>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Zustandsdaten</CardTitle>
            <CardDescription>
              Beobachtung aus der Integration (payload, ohne Secrets)
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs sm:grid-cols-3">
              <Field label="Status">
                <StatusBadge status={item.status} />
              </Field>
              <Field label="Beobachtet (UTC)">
                {formatDateTime(item.observed_at)}
                <span className="block text-[10px] text-muted-foreground">
                  {timeAgo(item.observed_at)}
                </span>
              </Field>
              <Field label="Letztmalig gesehen">
                {formatDateTime(item.last_seen_at)}
              </Field>
              <Field label="Erstmals gesehen">
                {formatDateTime(item.first_seen_at)}
              </Field>
              <Field label="Herkunft">
                <Badge variant="outline">{item.source}</Badge>
              </Field>
              <Field label="Ressourcen-ID">
                <span className="font-mono text-[10px]">{item.id}</span>
              </Field>
            </dl>
            <JsonView data={item.payload} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Beziehungen</CardTitle>
            <CardDescription>
              {item.relations.length === 0
                ? "Keine Beziehungen dokumentiert."
                : "Evidenz je Beziehung (API = verifiziert)"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {item.relations.length === 0 ? (
              <StatePanel
                state="empty"
                emptyText="Keine Beziehungen für diese Ressource vorhanden (keine erfunden)."
              />
            ) : (
              <ul className="flex flex-col gap-2">
                {item.relations.map((relation) => (
                  <li
                    key={relation.id}
                    className="rounded-md border border-border p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium">
                        {relation.source_name ??
                          relation.source_resource_id}
                        {" → "}
                        <Link
                          to={`/resources/${relation.target_resource_id}`}
                          className="text-primary hover:underline"
                        >
                          {relation.target_name ??
                            relation.target_resource_id}
                        </Link>
                      </span>
                      <Badge variant="outline">{relation.relation_type}</Badge>
                    </div>
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Evidenz: {sourceMeta(relation.evidence).label}
                      {relation.note !== null && ` — ${relation.note}`}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-start justify-between">
          <div>
            <CardTitle>Metriken</CardTitle>
            <CardDescription>
              CPU- und RAM-Zeitreihen über den gewählten Zeitraum
            </CardDescription>
          </div>
          <div
            role="group"
            aria-label="Zeitraum wählen"
            className="flex gap-1"
          >
            {ranges.map((range) => (
              <Button
                key={range.label}
                size="sm"
                variant={range.minutes === rangeMinutes ? "default" : "ghost"}
                aria-pressed={range.minutes === rangeMinutes}
                onClick={() => setRangeMinutes(range.minutes)}
              >
                {range.label}
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <MetricSection
            title="CPU"
            available={metric.data?.available ?? false}
            reason={metric.data?.reason}
            points={metric.data?.points ?? []}
            unit="%"
            color="#35b5a2"
          />
          <MetricSection
            title="RAM"
            available={metricMem.data?.available ?? false}
            reason={metricMem.data?.reason}
            points={metricMem.data?.points ?? []}
            unit="%"
            color="#818cf8"
          />
        </CardContent>
      </Card>

      {/*
        R0-Vertrag: keine VM/LXC-Aktions-Endpoints — daher blockiert
        (endpointAvailable=false, Vorschlag: docs/proposals/frontend-vm-actions.md).
      */}
      {action !== null && (
        <ActionDialog
          open={action !== null}
          onOpenChange={(open) => {
            if (!open) setAction(null);
          }}
          action={action}
          resourceName={item.name ?? item.external_id}
          endpointAvailable={false}
        />
      )}
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 text-xs">{children}</dd>
    </div>
  );
}

function MetricSection({
  title,
  available,
  reason,
  points,
  unit,
  color,
}: {
  title: string;
  available: boolean;
  reason?: string;
  points: { readonly ts: string; readonly value: number }[];
  unit: string;
  color: string;
}) {
  if (!available) {
    return (
      <div>
        <h3 className="mb-1 text-xs font-medium">{title}</h3>
        <StatePanel
          state="not_configured"
          notConfiguredText={
            reason ?? "Keine Metrik-Datenquelle konfiguriert."
          }
        />
      </div>
    );
  }
  return (
    <div>
      <h3 className="mb-1 text-xs font-medium">
        {title}{" "}
        {isDevFixture() && (
          <span className="text-status-degraded">· DEV-FIXTURE</span>
        )}
      </h3>
      <MetricChart label={title} points={points} unit={unit} color={color} />
    </div>
  );
}
