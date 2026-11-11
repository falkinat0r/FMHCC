import { useEffect, useRef, type ReactNode } from "react";

import { cn } from "../../lib/cn";
import { Button } from "./button";
import { X } from "lucide-react";

interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children?: ReactNode;
  className?: string;
}

/**
 * Zugangliches Modal (kein Radix: eigene, geprüfte Implementierung).
 * - role="dialog", aria-modal, aria-labelledby
 * - Escape schliesst, Fokus wird beim Oeffnen in den Dialog gelegt
 *   und beim Schliessen auf den ausloesenden Knopf zurueckgegeben.
 */
export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  className,
}: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onKey);
    // Fokussierung des Dialogs
    panelRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      restoreRef.current?.focus();
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Dialog schliessen"
        className="absolute inset-0 bg-black/60"
        onClick={() => onOpenChange(false)}
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="hcc-dialog-title"
        aria-describedby={description ? "hcc-dialog-desc" : undefined}
        tabIndex={-1}
        className={cn(
          "relative z-10 w-full max-w-lg rounded-lg border border-border bg-popover text-popover-foreground shadow-lg",
          className,
        )}
      >
        <div className="flex items-start justify-between gap-4 p-4">
          <div>
            <h2 id="hcc-dialog-title" className="text-sm font-semibold">
              {title}
            </h2>
            {description !== undefined && (
              <p
                id="hcc-dialog-desc"
                className="mt-1 text-xs text-muted-foreground"
              >
                {description}
              </p>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Dialog schliessen"
            onClick={() => onOpenChange(false)}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
        {children !== undefined && (
          <div className="border-t border-border p-4">{children}</div>
        )}
      </div>
    </div>
  );
}
