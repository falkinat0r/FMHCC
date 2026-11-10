import { useState, type FormEvent, type ReactElement } from "react";

import { api, ApiRequestError, type LoginResponse } from "../api/client";

interface LoginProps {
  onLoggedIn: () => Promise<void> | void;
}

/** R0-Shell-Login: nur echte v1-Endpoints, keine Mocks. */
export default function Login({ onLoggedIn }: LoginProps): ReactElement {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body: LoginResponse = await api.post("/auth/login", { username, password });
      void body.message; // Intentional: Antwort wird nur als Erfolgssignal genutzt
      await onLoggedIn();
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setError(`${err.message} (request ${err.requestId || "unbekannt"})`);
      } else {
        setError("Unerwarteter Fehler — bitte erneut versuchen.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="center">
      <form className="card login-form" onSubmit={(e) => void handleSubmit(e)}>
        <h1>HCC — Homelab Control Center</h1>
        <label>
          Benutzername
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
            minLength={1}
            maxLength={64}
          />
        </label>
        <label>
          Passwort
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            minLength={1}
            maxLength={200}
          />
        </label>
        {error !== null && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={busy}>
          {busy ? "Anmeldung läuft…" : "Anmelden"}
        </button>
      </form>
    </main>
  );
}
