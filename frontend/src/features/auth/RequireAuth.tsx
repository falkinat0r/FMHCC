import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthProvider";

/**
 * Schuetzt Routen: ohne gueltige Session wird zu /login umgeleitet
 * (Return-URL wird mitgegeben, damit die urspruengliche Seite nach
 * dem Login wieder aufgerufen werden kann).
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          Sitzung wird geprüft…
        </p>
      </main>
    );
  }

  if (status === "guest") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }

  return <>{children}</>;
}
