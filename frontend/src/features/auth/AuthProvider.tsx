import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";

import { useLogout, useSession } from "../../api/query";
import type { CurrentUserResponse } from "../../api/types";

interface AuthContextValue {
  /** "loading" | "guest" | "user" */
  status: "loading" | "guest" | "user";
  user: CurrentUserResponse | null;
  /** Session neu pruefen (nach Login). */
  refresh: () => Promise<void>;
  /** Logout (CSRF-geschuetzt); Session wird danach neu geprueft. */
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * Session-Provider. Prueft /auth/me (R0-Vertrag) und stellt den
 * Benutzer inkl. Rolle bereit. Bei 401/Feinfehler: ehrlich "guest"
 * — kein erfundener Login-Zustand.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const logoutMutation = useLogout();

  const refresh = useCallback(async () => {
    await session.refetch();
  }, [session]);

  const logout = useCallback(async () => {
    try {
      // Logout ist state-aendernd: CSRF-Header setzt der Client automatisch.
      await logoutMutation.mutateAsync();
    } catch {
      // Logout-Fehler darf die UI nicht blockieren — Session wird neu geprueft.
    }
    // Nach Logout liefert /auth/me 401 -> Status "guest".
    await session.refetch();
  }, [logoutMutation, session]);

  const value = useMemo<AuthContextValue>(() => {
    const user = session.data ?? null;
    const status: AuthContextValue["status"] = session.isPending
      ? "loading"
      : user !== null
        ? "user"
        : "guest";
    return {
      status,
      user,
      refresh,
      logout,
    };
  }, [session.data, session.isPending, refresh, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components -- Standard-Muster: Hook neben dem Context-Provider
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth muss innerhalb von <AuthProvider> verwendet werden");
  }
  return ctx;
}
