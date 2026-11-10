import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useIntegrations, useUpsertIntegration } from "../../api/query";
import { adapterInfo } from "./adapterInfo";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { Pagination } from "../../components/common/Pagination";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";
import { Dialog } from "../../components/ui/dialog";
import { Plus } from "lucide-react";
import { timeAgo } from "../../lib/format";
import { canAdmin } from "../../lib/permissions";
import { useAuth } from "../auth/AuthProvider";

const ADAPTER_OPTIONS = [
  "proxmox",
  "truenas",
  "pihole",
  "tailscale",
  "docker",
  "monitoring",
  "homeassistant",
] as const;

/**
 * Integrationsverwaltung (R0-Vertrag):
 * - GET /integrations (Liste)
 * - PUT /integrations/{id} (Konfigurieren — admin, CSRF)
 * - DELETE /integrations/{id} (admin, CSRF, Kaskade ueber Ressourcen)
 * - POST /integrations/{id}/verify (Detailseite)
 *
 * Es werden KEINE Funktionen angezeigt, die der Vertrag nicht
 * unterstuetzt.
 */
export default function IntegrationsPage() {
  const [page, setPage] = useState(1);
  const integrations = useIntegrations({ page, pageSize: 50 });
  const upsert = useUpsertIntegration();
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const navigate = useNavigate();

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    integration_id: "",
    name: "",
    adapter: "proxmox",
    base_url: "",
    secret_ref: "",
  });
  const [formError, setFormError] = useState<string | null>(null);

  const data = integrations.data;
  const items = data?.items ?? [];

  async function handleCreate(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFormError(null);
    const id = form.integration_id.trim();
    if (!/^[a-z0-9][a-z0-9-]*$/.test(id) || id.length < 3) {
      setFormError(
        "integration_id: 3–64 Zeichen, nur Kleinbuchstaben, Ziffern, Bindestriche (Erster kein -).",
      );
      return;
    }
    try {
      await upsert.mutateAsync({
        integrationId: id,
        body: {
          integration_id: id,
          name: form.name.trim(),
          adapter: form.adapter as (typeof ADAPTER_OPTIONS)[number],
          base_url: form.base_url.trim() === "" ? null : form.base_url.trim(),
          secret_ref: form.secret_ref.trim() === "" ? null : form.secret_ref.trim(),
        },
      });
      setCreateOpen(false);
      setForm({
        integration_id: "",
        name: "",
        adapter: "proxmox",
        base_url: "",
        secret_ref: "",
      });
      navigate(`/integrations/${id}`);
    } catch (err) {
      setFormError(describe(err));
    }
  }

  return (
    <div>
      <PageHeader
        title="Integrationen"
        description="Angebundene Systeme (read-only Liste; Konfiguration nur für admin)."
        actions={
          isAdmin && (
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              Neue Integration
            </Button>
          )
        }
      />

      <div className="flex flex-col gap-3">
        {integrations.isLoading && <StatePanel state="loading" rows={4} />}
        {integrations.error !== null &&
          queryStatePanel(integrations.error, () => void integrations.refetch())}
        {data !== undefined && items.length === 0 && (
          <StatePanel
            state="empty"
            emptyText="Noch keine Integrationen konfiguriert."
          />
        )}
        {items.length > 0 && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => {
              const info = adapterInfo(item.adapter);
              return (
                <Card key={item.id} className="flex flex-col">
                  <CardHeader className="flex-row items-start justify-between gap-2">
                    <div>
                      <CardTitle>
                        <Link
                          to={`/integrations/${item.integration_id}`}
                          className="hover:underline"
                        >
                          {item.name}
                        </Link>
                      </CardTitle>
                      <CardDescription>
                        {info.label} ·{" "}
                        <span className="font-mono">{item.integration_id}</span>
                      </CardDescription>
                    </div>
                    <StatusBadge status={item.status} />
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col gap-2 text-xs">
                    <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
                      <div>
                        <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          Base URL
                        </dt>
                        <dd className="truncate" title={item.base_url ?? undefined}>
                          {item.base_url ?? "n/v"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          Secret
                        </dt>
                        <dd className="font-mono">
                          {item.secret_ref ?? "—"}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          Letztes Verify
                        </dt>
                        <dd>{timeAgo(item.last_verified_at)}</dd>
                      </div>
                      <div>
                        <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                          Capabilities
                        </dt>
                        <dd>
                          {Object.keys(item.capabilities).length === 0
                            ? "— (noch keine)"
                            : Object.entries(item.capabilities)
                                .map(
                                  ([k, v]) =>
                                    `${k}:${v === true ? "✓" : v === false ? "—" : "•"}`,
                                )
                                .join("  ")}
                        </dd>
                      </div>
                    </dl>
                    {item.last_error !== null && (
                      <p
                        className="truncate text-status-down"
                        title={item.last_error}
                      >
                        {item.last_error}
                      </p>
                    )}
                    <div className="mt-auto flex justify-end">
                      <Link
                        to={`/integrations/${item.integration_id}`}
                        className="rounded px-2 py-1 text-xs text-primary hover:bg-accent"
                      >
                        Öffnen
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
        {data !== undefined && (
          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            onChange={setPage}
          />
        )}
      </div>

      <Dialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Neue Integration anlegen"
        description="Rein lokale Konfiguration — es findet hier KEIN Zugriff auf das Zielsystem statt. Verify ist ein separater, auditiertender Endpoint."
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => void handleCreate(e)}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="int-id">Integration-ID (Slug)</Label>
            <Input
              id="int-id"
              required
              minLength={3}
              maxLength={64}
              pattern="^[a-z0-9][a-z0-9-]*$"
              placeholder="z. B. proxmox-1"
              value={form.integration_id}
              onChange={(e) =>
                setForm((f) => ({ ...f, integration_id: e.target.value }))
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="int-name">Name</Label>
            <Input
              id="int-name"
              required
              minLength={1}
              maxLength={128}
              placeholder="z. B. Proxmox Haupt-Node"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="int-adapter">Adapter</Label>
            <Select
              id="int-adapter"
              value={form.adapter}
              onChange={(e) => setForm((f) => ({ ...f, adapter: e.target.value }))}
            >
              {ADAPTER_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {adapterInfo(opt).label}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="int-url">Base URL</Label>
            <Input
              id="int-url"
              type="url"
              placeholder="https://…"
              value={form.base_url}
              onChange={(e) =>
                setForm((f) => ({ ...f, base_url: e.target.value }))
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="int-secret">Secret-Ref (Name der Env-Variable)</Label>
            <Input
              id="int-secret"
              placeholder="z. B. HCC_PROXMOX_TOKEN"
              value={form.secret_ref}
              onChange={(e) =>
                setForm((f) => ({ ...f, secret_ref: e.target.value }))
              }
            />
            <p className="text-[10px] text-muted-foreground">
              Der Secret-Wert selbst wird NIE hier eingegeben — er verbleibt
              serverseitig in secrets.env (0640).
            </p>
          </div>
          {formError !== null && (
            <p role="alert" className="text-xs text-destructive">
              {formError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Abbrechen
            </Button>
            <Button type="submit" disabled={upsert.isPending}>
              {upsert.isPending ? "Wird gespeichert…" : "Speichern"}
            </Button>
          </div>
        </form>
      </Dialog>

    </div>
  );
}

function describe(err: unknown): string {
  if (err instanceof Error) return err.message;
  return "Unerwarteter Fehler";
}
