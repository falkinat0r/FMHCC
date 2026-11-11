import { useEffect, useRef, useState } from "react";
import { LogOut, UserCircle2 } from "lucide-react";

import { useAuth } from "../../features/auth/AuthProvider";
import { ROLE_LABEL } from "../../lib/permissions";
import { cn } from "../../lib/cn";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

/**
 * Benutzerbereich: Name, Rolle, Logout. Dropdown mit
 * Click-Outside- und Escape-Verhalten.
 */
export function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent): void {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent): void {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (user === null) return null;

  const role = user.role;

  async function handleLogout(): Promise<void> {
    setOpen(false);
    setBusy(true);
    try {
      await logout();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <Button
        variant="ghost"
        className="gap-2"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        <UserCircle2 className="h-4 w-4" aria-hidden="true" />
        <span className="max-w-28 truncate">{user.username}</span>
        <Badge variant="secondary" className="hidden sm:inline-flex">
          {role}
        </Badge>
      </Button>
      {open && (
        <div
          role="menu"
          aria-label="Benutzer-Menü"
          className={cn(
            "absolute right-0 z-40 mt-1 w-56 overflow-hidden rounded-md border border-border bg-popover shadow-lg",
          )}
        >
          <div className="border-b border-border p-3">
            <p className="truncate text-sm font-medium">{user.username}</p>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              {ROLE_LABEL[role]}
            </p>
            {user.must_change_password && (
              <p className="mt-1 text-[11px] text-status-degraded">
                Passwortwechsel erforderlich (Endpoint folgt per
                Contract-Proposal)
              </p>
            )}
          </div>
          <div role="none" className="p-1">
            <button
              role="menuitem"
              type="button"
              disabled={busy}
              className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm text-destructive hover:bg-accent"
              onClick={() => void handleLogout()}
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              {busy ? "Abmeldung…" : "Abmelden"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
