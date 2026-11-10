import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  useDeleteIntegration,
  useIntegration,
  useUpsertIntegration,
  useVerifyIntegration,
} from "../../api/query";
import type { VerifyResponse } from "../../api/types";
import { adapterInfo } from "./adapterInfo";
import { StatePanel, describeApiError, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
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
import { Badge } from "../../components/ui/badge";
import { ArrowLeft, LoaderCircle, ShieldCheck, Trash2 } from "lucide-react";
import { formatDateTime, timeAgo } from "../../lib/format";
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
 * Integrationsdetail (R0-Vertrag):
 * - GET /integrations/{id}
 * - PUT /integrations/{id} (Konfigurieren; admin + CSRF)
 * - POST /integrations/{id}/verify (admin + CSRF; lesende Prüfung)
 * - DELETE /integrations/{id} (admin + CSRF)
 *
 * RBAC: Verwaltung nur fuer admin (serverseitig gepraegt, UI spiegelt
 * nur dar).
 */
export default function IntegrationDetailPage() {
  const { integrationId } = useParams<{ integrationId: string }>();
  const integration = useIntegration(integrationId ?? "");
  const verify = useVerifyIntegration();
  const upsert = useUpsertIntegration();
  const remove = useDeleteIntegration();
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const navigate = useNavigate();

  const [verifyResult, setVerifyResult] = useState<VerifyResponse | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    adapter: "proxmox",
    base_url: "",
    secret_ref: "",
    initialized: false,
  });
  const [formError, setFormError] = useState<string | null>(null);

  if (integration.isLoading) {
    return <StatePanel state="loading" rows={6} />;
  }

  if (integration.error !== null || integration.data === undefined) {
    return (
      <div className="flex flex-col gap-3">
        <Link to="/integrations" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Zurueck zu Integrationen
        </Link>
        {queryStatePanel(
          integration.error ?? new Error("Integration nicht gefunden"),
          () => void integration.refetch(),
        )}
      </div>
    );
  }

  const item = integration.data;
  const info = adapterInfo(item.adapter);
  const id = item.integration_id;

  async function handleSave(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFormError(null);
    const adapter = form.adapter as (typeof ADAPTER_OPTIONS)[number];
    if (!ADAPTER_OPTIONS.includes(adapter)) {
      setFormError("Adapter ist ungültig.");
      return;
    }
    try {
      await upsert.mutateAsync({
        integrationId: id,
        body: {
          integration_id: id,
          name: form.name.trim(),
          adapter,
          base_url: form.base_url.trim() === "" ? null : form.base_url.trim(),
          secret_ref: form.secret_ref.trim() === "" ? null : form.secret_ref.trim(),
        },
      });
    } catch (err) {
      setFormError(describeApiError(err).message);
    }
  }

  async function handleVerify(): Promise<void> {
    setVerifyResult(null);
    try {
      const result = await verify.mutateAsync(id);
      setVerifyResult(result);
    } catch {
      setVerifyResult(null);
    }
  }

  async function handleDelete(): Promise<void> {
    try {
      await remove.mutateAsync(id);
      setDeleteOpen(false);
      navigate("/integrations");
    } catch {
      // Mutation-Fehler: Dialog bleibt geoeffnet, Status wird angezeigt.
    }
  }

  // Formular beim ersten Laden befuellen
  if (form.initialized !== true) {
    setForm({
      name: item.name,
      adapter: item.adapter,
      base_url: item.base_url ?? "",
      secret_ref: item.secret_ref ?? "",
      initialized: true,
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <Link
          to="/integrations"
          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
        >
          <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
          Zurueck zu Integrationen
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="text-lg font-semibold">{item.name}</h1>
          <StatusBadge status={item.status} />
          <Badge variant="outline">
            <span className="font-mono">{id}</span>
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {info.label} · erstellt {formatDateTime(item.created_at)} ·
          aktualisiert {formatDateTime(item.updated_at)}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Adapter-Beschreibung</CardTitle>
            <CardDescription>
              Was diese Anbindung in HCC leisten kann (statisch, pro Adapter-Typ)
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-xs">{info.summary}</p>
            <div className="mt-3">
              <h3 className="mb-1 text-[11px] font-medium text-muted-foreground">
                Aktive Capabilities (aus der API)
              </h3>
              {Object.keys(item.capabilities).length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Keine Capabilities bekannt — Verify ausführen, um sie zu
                  ermitteln (falls Adapter implementiert ist).
                </p>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {Object.entries(item.capabilities).map(([key, value]) => (
                    <li key={key}>
                      <Badge variant={value === true ? "default" : "outline"}>
                        {key}: {value === true ? "ja" : value === false ? "nein" : "•"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Konfiguration</CardTitle>
            <CardDescription>
              {isAdmin
                ? "Rein lokale Konfiguration — kein Zugriff auf das Zielsystem. Speichern (admin, CSRF)."
                : "Nur Lesezugriff — Konfiguration erfordert die Rolle admin."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-3" onSubmit={(e) => void handleSave(e)}>
              <div className="flex flex-col gap-1">
                <Label htmlFor="cfg-name">Name</Label>
                <Input
                  id="cfg-name"
                  required
                  minLength={1}
                  maxLength={128}
                  disabled={!isAdmin}
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="cfg-adapter">Adapter</Label>
                <Select
                  id="cfg-adapter"
                  disabled={!isAdmin}
                  value={form.adapter}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, adapter: e.target.value }))
                  }
                >
                  {ADAPTER_OPTIONS.map((opt) => (
                    <option key={opt} value={opt}>
                      {adapterInfo(opt).label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="cfg-url">Base URL</Label>
                <Input
                  id="cfg-url"
                  type="url"
                  disabled={!isAdmin}
                  value={form.base_url}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, base_url: e.target.value }))
                  }
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="cfg-secret">Secret-Ref</Label>
                <Input
                  id="cfg-secret"
                  disabled={!isAdmin}
                  value={form.secret_ref}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, secret_ref: e.target.value }))
                  }
                />
                <p className="text-[10px] text-muted-foreground">
                  Nur der Name der Env-Variable — Secret-Werte verbleiben in
                  /etc/hcc/secrets.env (0640) und werden niemals übertragen.
                </p>
              </div>
              {formError !== null && (
                <p role="alert" className="text-xs text-destructive">
                  {formError}
                </p>
              )}
              {isAdmin && (
                <div className="flex justify-end">
                  <Button type="submit" disabled={upsert.isPending}>
                    {upsert.isPending ? "Wird gespeichert…" : "Speichern"}
                  </Button>
                </div>
              )}
            </form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <div>
            <CardTitle>Verbindung prüfen (Verify)</CardTitle>
            <CardDescription>
              Lesende Prüfungsanfrage an das Zielsystem; wird auditiert.
              Im R0 ist die Adapter-Registry leer → 501 not_implemented.
            </CardDescription>
          </div>
          <div className="flex gap-2">
            {isAdmin ? (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={verify.isPending}
                  onClick={() => void handleVerify()}
                >
                  {verify.isPending && (
                    <LoaderCircle className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  )}
                  <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                  Verify
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setDeleteOpen(true)}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                  Löschen
                </Button>
              </>
            ) : (
              <Badge variant="outline">RBAC: admin erforderlich</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="text-xs">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-4">
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Status
              </dt>
              <dd>
                <StatusBadge status={item.status} />
              </dd>
            </div>
            <div>
              <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Letztes Verify
              </dt>
              <dd>
                {item.last_verified_at === null
                  ? "noch nie geprüft"
                  : `${timeAgo(item.last_verified_at)} (${formatDateTime(item.last_verified_at)})`}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                Letzter Fehler
              </dt>
              <dd className={item.last_error !== null ? "text-status-down" : ""}>
                {item.last_error ?? "—"}
              </dd>
            </div>
          </dl>

          {verify.error !== null && (
            <div className="mt-3">
              <StatePanel
                state="error"
                error={describeApiError(verify.error).message}
                requestId={describeApiError(verify.error).requestId}
              />
            </div>
          )}

          {verifyResult !== null && (
            <div className="mt-3 rounded-md border border-border bg-muted/30 p-3">
              <p className="mb-1 flex items-center gap-2 text-xs font-medium">
                Verify-Ergebnis
                <Badge
                  variant={verifyResult.status === "ok" ? "default" : "destructive"}
                >
                  {verifyResult.status}
                </Badge>
              </p>
              {verifyResult.message !== null && (
                <p className="text-xs">{verifyResult.message}</p>
              )}
              <p className="mt-1 text-[10px] text-muted-foreground">
                geprüft {formatDateTime(verifyResult.checked_at)}
                {verifyResult.api_version !== null &&
                  ` · API-Version: ${verifyResult.api_version}`}
              </p>
              {Object.keys(verifyResult.capabilities).length > 0 && (
                <ul className="mt-2 flex flex-wrap gap-1.5">
                  {Object.entries(verifyResult.capabilities).map(([k, v]) => (
                    <li key={k}>
                      <Badge variant={v === true ? "default" : "outline"}>
                        {k}: {v === true ? "ja" : "nein"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Integration löschen"
        description="Alle zugehörigen Ressourcen werden kaskadierend gelöscht."
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm">
            Möchten Sie <strong>{item.name}</strong> endgültig löschen?
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Abbrechen
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => void handleDelete()}
            >
              {remove.isPending ? "Wird gelöscht…" : "Löschen"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
