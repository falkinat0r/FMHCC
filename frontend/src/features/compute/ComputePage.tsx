import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useIntegrations, useResources } from "../../api/query";
import type { ResourceOut } from "../../api/types";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { Pagination } from "../../components/common/Pagination";
import { Tabs } from "../../components/ui/tabs";
import { Input } from "../../components/ui/input";
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
import { formatTime, timeAgo } from "../../lib/format";
import { RESOURCE_STATUS } from "../../lib/status";
import { cn } from "../../lib/cn";

type TabValue = "host" | "vm" | "lxc" | "container";

const TABS = [
  { value: "host", label: "Hosts" },
  { value: "vm", label: "VMs" },
  { value: "lxc", label: "LXC" },
  { value: "container", label: "Container" },
] as const;

/**
 * Compute-Management (read-only, R0-Vertrag):
 * Hostliste, VM-Tabelle, LXC-Tabelle, Container, Ressourcenfilter
 * (Status, Integration, Suche) — alles ueber GET /api/v1/resources.
 *
 * Verwaltungsaktionen sind nicht Teil des R0-Vertrags (keine
 * Endpunkte) und werden in der Detailansicht entsprechend
 * gekennzeichnet (docs/proposals/frontend-vm-actions.md).
 */
export default function ComputePage() {
  const [tab, setTab] = useState<TabValue>("vm");
  const [status, setStatus] = useState("");
  const [integration, setIntegration] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const navigate = useNavigate();

  const integrationsQuery = useIntegrations({ page: 1, pageSize: 200 });
  const resources = useResources({
    resourceType: tab,
    status: status || null,
    integration: integration || null,
    q: q.trim() === "" ? null : q.trim(),
    page,
    pageSize: 50,
  });

  const data = resources.data;
  const rows = data?.items ?? [];

  const filteredCount = data?.total ?? 0;

  const integrationOptions = useMemo(
    () => integrationsQuery.data?.items ?? [],
    [integrationsQuery.data],
  );

  return (
    <div>
      <PageHeader
        title="Compute"
        description="Physische Hosts, VMs und Container — read-only Inventar aus den Integrationen (R0-Vertrag)."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Tabs tabs={[...TABS]} value={tab} onChange={(v) => {
          setTab(v as TabValue);
          setPage(1);
        }} />
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex flex-col gap-1">
            <Label htmlFor="compute-status">Status</Label>
            <Select
              id="compute-status"
              className="w-40"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Alle</option>
              {Object.entries(RESOURCE_STATUS).map(([value, meta]) => (
                <option key={value} value={value}>
                  {meta.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="compute-integration">Integration</Label>
            <Select
              id="compute-integration"
              className="w-44"
              value={integration}
              onChange={(e) => {
                setIntegration(e.target.value);
                setPage(1);
              }}
            >
              <option value="">Alle</option>
              {integrationOptions.map((item) => (
                <option key={item.id} value={item.integration_id}>
                  {item.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="compute-q">Suche</Label>
            <Input
              id="compute-q"
              className="w-44"
              placeholder="Name…"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        {resources.isLoading && (
          <StatePanel state="loading" rows={6} />
        )}
        {resources.error !== null &&
          queryStatePanel(resources.error, () => void resources.refetch())}
        {data !== undefined && rows.length === 0 && (
          <StatePanel
            state="empty"
            emptyText={
              filteredCount === 0
                ? `Keine ${TABS.find((t) => t.value === tab)?.label ?? ""} gefunden${
                    integration !== "" ? " (Filter: Integration)" : ""
                  }.`
                : "Keine Ressourcen."
            }
          />
        )}
        {rows.length > 0 && (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>External-ID</TableHead>
                  <TableHead>Integration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Quelle</TableHead>
                  <TableHead>Beobachtet (UTC)</TableHead>
                  <TableHead className="text-right">Aktion</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row) => (
                  <ResourceRow
                    key={row.id}
                    row={row}
                    onOpen={() => navigate(`/resources/${row.id}`)}
                  />
                ))}
              </TableBody>
            </Table>
            <Pagination
              page={data?.page ?? 1}
              totalPages={data?.total_pages ?? 1}
              total={data?.total ?? 0}
              onChange={setPage}
            />
          </>
        )}
      </div>
    </div>
  );
}

function ResourceRow({
  row,
  onOpen,
}: {
  row: ResourceOut;
  onOpen: () => void;
}) {
  const meta = RESOURCE_STATUS[row.status] ?? RESOURCE_STATUS.unknown;
  return (
    <TableRow>
      <TableCell>
        <button
          type="button"
          onClick={onOpen}
          className={cn(
            "flex items-center gap-2 rounded text-left text-sm font-medium hover:underline",
          )}
          aria-label={`Details zu ${row.name ?? row.external_id} oeffnen`}
        >
          <span
            aria-hidden="true"
            className={cn("h-2 w-2 shrink-0 rounded-full", meta.dotClass)}
          />
          {row.name ?? row.external_id}
        </button>
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {row.external_id}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {row.integration_id}
      </TableCell>
      <TableCell>
        <StatusBadge status={row.status} />
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {row.source}
      </TableCell>
      <TableCell>
        <span
          className="block text-xs text-muted-foreground"
          title={
            row.observed_at === null
              ? undefined
              : `${formatTime(row.observed_at)} (UTC)`
          }
        >
          {timeAgo(row.observed_at)}
          <span className="block text-[10px]">{formatTime(row.observed_at)}</span>
        </span>
      </TableCell>
      <TableCell className="text-right">
        <button
          type="button"
          onClick={onOpen}
          className="rounded px-2 py-1 text-xs text-primary hover:bg-accent"
        >
          Details
        </button>
      </TableCell>
    </TableRow>
  );
}
