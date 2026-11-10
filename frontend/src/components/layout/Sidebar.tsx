import { NavLink } from "react-router-dom";

import { cn } from "../../lib/cn";
import { canAdmin } from "../../lib/permissions";
import { useAuth } from "../../features/auth/AuthProvider";
import { Server } from "lucide-react";
import { NAV_SECTIONS } from "./nav";

/**
 * Sidebar-Navigation. Active-Item wird via NavLink (aria-current)
 * markiert. Admin-only-Eintraege werden je Rolle ausgeblendet.
 */
export function Sidebar({ className }: { className?: string }) {
  const { user } = useAuth();
  const isAdmin = canAdmin(user?.role);

  return (
    <nav
      aria-label="Hauptnavigation"
      className={cn(
        "flex h-full w-52 shrink-0 flex-col border-r border-border bg-card",
        className,
      )}
    >
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Server className="h-5 w-5 text-primary" aria-hidden="true" />
        <div>
          <p className="text-sm font-bold leading-none text-primary">HCC</p>
          <p className="mt-0.5 text-[10px] leading-none text-muted-foreground">
            Homelab Control Center
          </p>
        </div>
      </div>

      {NAV_SECTIONS.map((section) => {
        const items = section.items.filter(
          (item) => item.adminOnly !== true || isAdmin,
        );
        if (items.length === 0) return null;
        return (
          <div key={section.title} className="px-2 py-3">
            <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {section.title}
            </p>
            <ul className="flex flex-col gap-0.5">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === "/"}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                        isActive
                          ? "bg-accent font-medium text-foreground"
                          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                      )
                    }
                  >
                    <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      <div className="mt-auto border-t border-border px-4 py-3">
        <p className="text-[10px] text-muted-foreground">
          R1 · API v1 (frozen R0-Vertrag)
        </p>
      </div>
    </nav>
  );
}
