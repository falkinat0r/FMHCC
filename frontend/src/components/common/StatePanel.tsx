import type { ReactNode } from "react";

import { AlertTriangle, RefreshCw } from "lucide-react";

import { cn } from "../../lib/cn";
import { ApiRequestError } from "../../api/client";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";

/**
 * Einheitliche Zustaeinde aller Datenbereiche:
 * loading | error | empty | not_configured.
 *
 * - error: zeigt die Error-Envelope-Nachricht + Request-ID (Debug)
 * - empty: "keine Daten" (ehrlich, keine Fixtures)
 * - not_configured: Funktion/Quelle ist noch nicht eingerichtet
 */

export interface StatePanelProps {
  state: "loading" | "error" | "empty" | "not_configured";
  /** Fehlermeldung (state=error) */
  error?: string;
  /** Request-ID des fehlgeschlagenen Requests */
  requestId?: string;
  /** Text fuer empty */
  emptyText?: ReactNode;
  /** Text fuer not_configured */
  notConfiguredText?: ReactNode;
  /** Optionaler Retry-Callback (state=error) */
  onRetry?: () => void;
  className?: string;
  rows?: number;
}

// eslint-disable-next-line react-refresh/only-export-components -- bewusst in dieser Datei: Fehler-Beschreibung gehoert zur StatePanel-Logik
export function describeApiError(error: unknown): {
  message: string;
  requestId: string;
} {
  if (error instanceof ApiRequestError) {
    return {
      message: error.message,
      requestId: error.requestId,
    };
  }
  if (error instanceof Error) {
    return { message: error.message, requestId: "" };
  }
  return { message: "Unerwarteter Fehler", requestId: "" };
}

export function StatePanel({
  state,
  error,
  requestId,
  emptyText = "Keine Eintraege.",
  notConfiguredText = "Nicht konfiguriert.",
  onRetry,
  className,
  rows = 4,
}: StatePanelProps) {
  if (state === "loading") {
    return (
      <div
        className={cn("flex flex-col gap-2", className)}
        aria-busy="true"
        aria-label="Wird geladen"
      >
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }

  if (state === "error") {
    return (
      <div
        role="alert"
        className={cn(
          "flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3",
          className,
        )}
      >
        <div className="flex items-center gap-2 text-sm font-medium text-destructive">
          <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          Fehler bei der Datenabfrage
        </div>
        <p className="text-xs text-foreground">{error ?? "Unbekannter Fehler"}</p>
        {requestId !== "" && (
          <p className="text-[11px] text-muted-foreground">
            Request-ID: <span className="font-mono">{requestId}</span>
          </p>
        )}
        {onRetry !== undefined && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Erneut versuchen
          </Button>
        )}
      </div>
    );
  }

  if (state === "empty") {
    return (
      <p
        className={cn(
          "rounded-md border border-dashed border-border p-3 text-center text-xs text-muted-foreground",
          className,
        )}
      >
        {emptyText}
      </p>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-1 rounded-md border border-border bg-muted/30 p-3",
        className,
      )}
    >
      <p className="text-xs font-medium text-muted-foreground">
        {notConfiguredText}
      </p>
    </div>
  );
}

/** Kapselung: Query-Zustand -> StatePanel (inkl. Error-Beschreibung). */
// eslint-disable-next-line react-refresh/only-export-components -- Helper, der StatePanel kapselt
export function queryStatePanel(
  error: unknown,
  onRetry?: () => void,
): ReactNode {
  const { message, requestId } = describeApiError(error);
  return (
    <StatePanel
      state="error"
      error={message}
      requestId={requestId}
      onRetry={onRetry}
    />
  );
}
