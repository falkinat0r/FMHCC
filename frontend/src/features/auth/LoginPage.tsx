import { useState, type FormEvent, type ReactElement } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { api, ApiRequestError } from "../../api/client";
import { useAuth } from "./AuthProvider";
import { Server } from "lucide-react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../../components/ui/card";

/**
 * Login (R0-Vertrag: POST /api/v1/auth/login, session Cookie).
 * Fehler kommen zentral aus der Error-Envelope.
 */
export default function LoginPage(): ReactElement {
  const { status, refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from =
    (location.state as { from?: string } | null)?.from ?? "/";

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "user") {
    return <Navigate to={from} replace />;
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      // Login ist CSRF-exempt (R0-Vertrag); Client setzt Header ohnehin korrekt.
      await api.post("/auth/login", { username, password });
      await refresh();
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(
          `${err.message} (request ${err.requestId === "" ? "unbekannt" : err.requestId})`,
        );
      } else {
        setError("Unerwarteter Fehler — bitte erneut versuchen.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="mb-2 flex items-center gap-2">
            <Server className="h-5 w-5 text-primary" aria-hidden="true" />
            <span className="text-base font-bold text-primary">HCC</span>
          </div>
          <CardTitle>Homelab Control Center</CardTitle>
          <CardDescription>
            Anmeldung mit Benutzername und Passwort (serverseitige Session)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={(e) => void handleSubmit(e)}>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-username">Benutzername</Label>
              <Input
                id="login-username"
                name="username"
                autoComplete="username"
                required
                minLength={1}
                maxLength={64}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="login-password">Passwort</Label>
              <Input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                minLength={1}
                maxLength={200}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error !== null && (
              <p
                role="alert"
                className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive"
              >
                {error}
              </p>
            )}
            <Button type="submit" disabled={busy}>
              {busy ? "Anmeldung läuft…" : "Anmelden"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
