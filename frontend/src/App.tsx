import { useCallback, useEffect, useState, type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { api, ApiRequestError, type CurrentUserResponse } from "./api/client";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";

type AuthState =
  | { status: "loading" }
  | { status: "guest" }
  | { status: "user"; user: CurrentUserResponse };

/**
 * R0-Shell: prueft die Session einmalig (/auth/me) und routet danach.
 * Die Session-Pruefung ist bewusst minimal — Agent 2 baut die
 * eigentliche UI-Struktur (Layout, Navigation, Feature-Modulen) auf.
 */
export default function App(): ReactElement {
  const [auth, setAuth] = useState<AuthState>({ status: "loading" });

  const refresh = useCallback(async () => {
    try {
      const user = await api.get<CurrentUserResponse>("/auth/me");
      setAuth({ status: "user", user });
    } catch (error) {
      if (error instanceof ApiRequestError && error.code === "unauthenticated") {
        setAuth({ status: "guest" });
      } else {
        // Unerwarteter Fehler: Session-Zustand bleibt unklaer — als Gast
        // behandeln, kein erfundener Login-Zustand.
        setAuth({ status: "guest" });
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  if (auth.status === "loading") {
    return (
      <main className="center">
        <p className="muted">Sitzung wird geprüft…</p>
      </main>
    );
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={auth.status === "user" ? <Navigate to="/" replace /> : <Login onLoggedIn={refresh} />}
      />
      <Route
        path="/"
        element={
          auth.status === "user" ? (
            <Dashboard user={auth.user} onLoggedOut={refresh} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
