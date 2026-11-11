import { useState, type FormEvent } from "react";

import {
  useCreateUser,
  useUpdateUser,
  useUsers,
} from "../../api/query";
import type { Role, UserOut } from "../../api/types";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, describeApiError, queryStatePanel } from "../../components/common/StatePanel";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import { Plus } from "lucide-react";
import { formatDateTime, timeAgo } from "../../lib/format";
import { canAdmin, ROLE_LABEL } from "../../lib/permissions";
import { useAuth } from "../auth/AuthProvider";

const ROLES: Role[] = ["viewer", "operator", "admin"];

/**
 * Einstellungen (R0-Vertrag):
 * - Eigene Account-Infos (GET /auth/me)
 * - Benutzer (GET/POST /users, PATCH /users/{id}) — nur admin
 *
 * Hinweis: Passwortwechsel-Endpunkt existiert nicht im R0-Vertrag
 * (Proposal: docs/proposals/frontend-password-change.md).
 */
export default function SettingsPage() {
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);
  const users = useUsers({ page: 1, pageSize: 50 });

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<UserOut | null>(null);
  const [createForm, setCreateForm] = useState({
    username: "",
    display_name: "",
    role: "viewer",
    password: "",
  });
  const [editForm, setEditForm] = useState({
    display_name: "",
    role: "viewer",
    is_active: true,
  });
  const [formError, setFormError] = useState<string | null>(null);

  const createUser = useCreateUser();
  const updateUser = useUpdateUser();

  const items = users.data?.items ?? [];

  async function handleCreate(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setFormError(null);
    try {
      await createUser.mutateAsync({
        username: createForm.username.trim(),
        display_name: createForm.display_name.trim() === "" ? null : createForm.display_name.trim(),
        role: createForm.role as Role,
        password: createForm.password,
      });
      setCreateOpen(false);
      setCreateForm({ username: "", display_name: "", role: "viewer", password: "" });
    } catch (err) {
      setFormError(describeApiError(err).message);
    }
  }

  async function handleEdit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (editTarget === null) return;
    setFormError(null);
    try {
      await updateUser.mutateAsync({
        userId: editTarget.id,
        body: {
          display_name: editForm.display_name.trim() === "" ? null : editForm.display_name.trim(),
          role: editForm.role as Role,
          is_active: editForm.is_active,
        },
      });
      setEditTarget(null);
    } catch (err) {
      setFormError(describeApiError(err).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="Einstellungen"
        description="Account und Benutzerverwaltung (RBAC)."
      />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Mein Account</CardTitle>
            <CardDescription>
              Angaben aus GET /api/v1/auth/me
            </CardDescription>
          </CardHeader>
          <CardContent>
            {user === null ? (
              <StatePanel state="loading" rows={2} />
            ) : (
              <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Benutzername
                  </dt>
                  <dd>{user.username}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Anzeigename
                  </dt>
                  <dd>{user.display_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Rolle
                  </dt>
                  <dd>
                    <Badge variant="secondary">{user.role}</Badge>{" "}
                    <span className="text-muted-foreground">
                      {ROLE_LABEL[user.role]}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
                    Letzter Login
                  </dt>
                  <dd>{timeAgo(user.last_login_at)}</dd>
                </div>
              </dl>
            )}
            {user !== null && user.must_change_password === true && (
              <p className="mt-3 rounded-md border border-status-degraded/40 bg-status-degraded/10 p-2 text-xs text-status-degraded">
                Passwortwechsel erforderlich — ein Endpunkt dafür ist im
                R0-Vertrag noch nicht vorhanden (Contract-Proposal:
                frontend-password-change).
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex-row items-start justify-between gap-2">
            <div>
              <CardTitle>Benutzer</CardTitle>
              <CardDescription>
                {isAdmin
                  ? "Anlegen und bearbeiten (admin, CSRF-geschützt)"
                  : "Nicht verfügbar — Benutzerverwaltung erfordert die Rolle admin."}
              </CardDescription>
            </div>
            {isAdmin && (
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                Benutzer
              </Button>
            )}
          </CardHeader>
          <CardContent>
            {!isAdmin ? (
              <StatePanel
                state="not_configured"
                notConfiguredText="Benutzerverwaltung ist nur für die Rolle admin verfügbar (serverseitige RBAC-Prüfung)."
              />
            ) : users.isLoading ? (
              <StatePanel state="loading" rows={3} />
            ) : users.error !== null ? (
              queryStatePanel(users.error, () => void users.refetch())
            ) : items.length === 0 ? (
              <StatePanel state="empty" emptyText="Keine Benutzer vorhanden." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Benutzer</TableHead>
                    <TableHead>Rolle</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Letzter Login</TableHead>
                    <TableHead className="text-right">Aktion</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <span className="block text-sm font-medium">
                          {item.username}
                        </span>
                        <span className="block text-[10px] text-muted-foreground">
                          {item.display_name ?? "—"} · erstellt{" "}
                          {formatDateTime(item.created_at)}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{item.role}</Badge>
                      </TableCell>
                      <TableCell>
                        {item.is_active ? (
                          <Badge variant="default">aktiv</Badge>
                        ) : (
                          <Badge variant="destructive">deaktiviert</Badge>
                        )}
                        {item.must_change_password && (
                          <span className="ml-1 text-[10px] text-status-degraded">
                            PW-Wechsel fällig
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {timeAgo(item.last_login_at)}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditTarget(item);
                            setEditForm({
                              display_name: item.display_name ?? "",
                              role: item.role,
                              is_active: item.is_active,
                            });
                            setFormError(null);
                          }}
                        >
                          Bearbeiten
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title="Benutzer anlegen"
        description="Das Initialpasswort muss beim ersten Login geändert werden."
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => void handleCreate(e)}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="user-username">Benutzername</Label>
            <Input
              id="user-username"
              required
              minLength={3}
              maxLength={64}
              pattern="^[a-z0-9][a-z0-9._-]*$"
              placeholder="z. B. ops1"
              value={createForm.username}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, username: e.target.value }))
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="user-name">Anzeigename (optional)</Label>
            <Input
              id="user-name"
              maxLength={128}
              value={createForm.display_name}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, display_name: e.target.value }))
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="user-role">Rolle</Label>
            <Select
              id="user-role"
              value={createForm.role}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, role: e.target.value as Role }))
              }
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="user-password">Passwort</Label>
            <Input
              id="user-password"
              type="password"
              required
              minLength={10}
              maxLength={200}
              autoComplete="new-password"
              value={createForm.password}
              onChange={(e) =>
                setCreateForm((f) => ({ ...f, password: e.target.value }))
              }
            />
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
            <Button type="submit" disabled={createUser.isPending}>
              {createUser.isPending ? "Wird angelegt…" : "Anlegen"}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={editTarget !== null}
        onOpenChange={(open) => {
          if (!open) setEditTarget(null);
        }}
        title={
          editTarget !== null
            ? `Benutzer bearbeiten: ${editTarget.username}`
            : "Benutzer bearbeiten"
        }
        description="Änderungen werden auditiert. Der letzte Admin kann nicht deaktiviert werden (serverseitiger Schutz)."
      >
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => void handleEdit(e)}
        >
          <div className="flex flex-col gap-1">
            <Label htmlFor="edit-name">Anzeigename</Label>
            <Input
              id="edit-name"
              maxLength={128}
              value={editForm.display_name}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, display_name: e.target.value }))
              }
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label htmlFor="edit-role">Rolle</Label>
            <Select
              id="edit-role"
              value={editForm.role}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, role: e.target.value as Role }))
              }
            >
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </Select>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={editForm.is_active}
              onChange={(e) =>
                setEditForm((f) => ({ ...f, is_active: e.target.checked }))
              }
              className="h-3.5 w-3.5 accent-[var(--color-primary)]"
            />
            Benutzer aktiv
          </label>
          {formError !== null && (
            <p role="alert" className="text-xs text-destructive">
              {formError}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setEditTarget(null)}
            >
              Abbrechen
            </Button>
            <Button type="submit" disabled={updateUser.isPending}>
              {updateUser.isPending ? "Wird gespeichert…" : "Speichern"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
