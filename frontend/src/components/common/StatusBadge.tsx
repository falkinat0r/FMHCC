import { statusMeta } from "../../lib/status";
import { cn } from "../../lib/cn";
import { Badge } from "../ui/badge";

interface StatusBadgeProps {
  /** R0-Contract-Zustand (healthy|degraded|down|unknown|not_configured) */
  status: string;
  className?: string;
}

/**
 * Einheitliche Status-Kennzeichnung. Zeigt exakt die funf
 * fachlichen Zustaeinde an; unbekannte Werte fallen auf "unknown"
 * zurueck (kein Ratespiel).
 */
export function StatusBadge({ status, className }: StatusBadgeProps) {
  const meta = statusMeta(status);
  return (
    <Badge
      variant="status"
      className={cn(meta.badgeClass, className)}
      data-status={status}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full ${meta.dotClass}`}
      />
      {meta.label}
    </Badge>
  );
}
