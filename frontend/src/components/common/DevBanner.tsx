import { FlaskConical } from "lucide-react";

/**
 * Dauerhafter Banner fuer den gekennzeichneten Entwicklungsmodus
 * (DEV-FIXTURE). Solange aktiv, sind alle dargestellten Daten
 * Fixtures — niemals Echtdaten (AGENTS.md Regel 7).
 */
export function DevBanner() {
  return (
    <div
      role="status"
      aria-label="Entwicklungsmodus aktiv"
      className="flex items-center justify-center gap-2 bg-status-degraded px-4 py-1.5 text-xs font-semibold text-background"
    >
      <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
      DEV-FIXTURE MODUS — alle Daten sind klar markierte Test-Fixtures,
      keine echten Infrastrukturdaten
    </div>
  );
}
