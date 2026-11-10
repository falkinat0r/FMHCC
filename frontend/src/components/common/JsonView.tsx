import { useState } from "react";

import { ChevronDown, ChevronRight } from "lucide-react";

import { cn } from "../../lib/cn";

/**
 * Read-only JSON-Anzeige fuer `payload`-Felder (frei definiert,
 * aber ohne Secrets — Contract-Vorgabe).
 */
export function JsonView({
  data,
  className,
}: {
  data: unknown;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const entries =
    typeof data === "object" && data !== null
      ? Object.entries(data as Record<string, unknown>)
      : [];

  if (entries.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">Keine Payload-Daten.</p>
    );
  }

  return (
    <div className={cn("rounded-md border border-border", className)}>
      <button
        type="button"
        className="flex w-full items-center gap-1 p-2 text-left text-xs font-medium text-muted-foreground hover:bg-muted/40"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        )}
        Details (JSON, {entries.length} Felder)
      </button>
      {open && (
        <pre
          className="overflow-auto border-t border-border p-2 font-mono text-[11px] leading-relaxed"
          aria-label="JSON-Inhalt"
        >
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
