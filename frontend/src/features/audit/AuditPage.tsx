import { useState } from "react";

import { useAudit } from "../../api/query";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { Pagination } from "../../components/common/Pagination";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { formatDateTime } from "../../lib/format";
import { JsonView } from "../../components/common/JsonView";
import { useAuth } from "../auth/AuthProvider";
import { canAdmin } from "../../lib/permissions";

/**
 * Audit-Log (GET /api/v1/audit, append-only, nur admin).
 * Details-Feld ist serverseitig maskiert — wird unveraendert gezeigt.
 */
export default function AuditPage() {
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [username, setUsername] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  const audit = useAudit({
    page,
    pageSize: 50,
    action: action.trim() === "" ? null : action.trim(),
    username: username.trim() === "" ? null : username.trim(),
  });

  if (!isAdmin) {
    return (
      <div>
        <PageHeader title="Audit-Log" />
        <StatePanel
          state="not_configured"
          notConfiguredText="Das Audit-Log ist nur für die Rolle admin lesbar (RBAC, serverseitig geprüft)."
        />
      </div>
    );
  }

  const items = audit.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="Audit-Log"
        description="Alle auditierten Aktionen (append-only). Details werden serverseitig maskiert."
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <Label htmlFor="audit-action">Aktion (Präfix)</Label>
          <Input
            id="audit-action"
            className="w-48"
            placeholder="z. B. auth.login"
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor="audit-username">Benutzer</Label>
          <Input
            id="audit-username"
            className="w-40"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Events</CardTitle>
          <CardDescription>
            {audit.data !== undefined
              ? `${audit.data.total} Events, Seite ${audit.data.page}/${audit.data.total_pages}`
              : "…"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {audit.isLoading && <StatePanel state="loading" rows={6} />}
          {audit.error !== null &&
            queryStatePanel(audit.error, () => void audit.refetch())}
          {audit.data !== undefined && items.length === 0 && (
            <StatePanel state="empty" emptyText="Keine Audit-Events (Filter passen nicht?)." />
          )}
          {items.length > 0 && (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Zeit (UTC)</TableHead>
                    <TableHead>Aktion</TableHead>
                    <TableHead>Benutzer</TableHead>
                    <TableHead>Ressource</TableHead>
                    <TableHead>IP</TableHead>
                    <TableHead className="text-right">Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((event) => (
                    <TableRow key={event.id}>
                      <TableCell className="whitespace-nowrap text-xs">
                        {formatDateTime(event.created_at)}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{event.action}</TableCell>
                      <TableCell className="text-xs">{event.username ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {event.resource_type !== null
                          ? `${event.resource_type}/${event.resource_id ?? "?"}`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {event.ip_address ?? "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <button
                          type="button"
                          className="rounded px-2 py-1 text-xs text-primary hover:bg-accent"
                          aria-expanded={expanded === event.id}
                          onClick={() =>
                            setExpanded(expanded === event.id ? null : event.id)
                          }
                        >
                          {expanded === event.id ? "Ausblenden" : "Details"}
                        </button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {expanded !== null && (
                <div className="mt-3">
                  <JsonView
                    data={
                      items.find((e) => e.id === expanded)?.details ?? {}
                    }
                  />
                </div>
              )}
              <div className="mt-3">
                <Pagination
                  page={audit.data?.page ?? 1}
                  totalPages={audit.data?.total_pages ?? 1}
                  total={audit.data?.total ?? 0}
                  onChange={setPage}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
