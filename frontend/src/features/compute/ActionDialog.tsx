import { AlertTriangle, LoaderCircle } from "lucide-react";

import { Button } from "../../components/ui/button";
import { Dialog } from "../../components/ui/dialog";

export type ComputeAction = "start" | "stop" | "reboot";

// eslint-disable-next-line react-refresh/only-export-components -- Label-Konstanten gehoeren zur ActionDialog-Domäne
export const ACTION_LABEL: Record<ComputeAction, string> = {
  start: "Starten",
  stop: "Sanftes Herunterfahren",
  reboot: "Neu starten",
};

interface ActionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  action: ComputeAction;
  resourceName: string;
  /**
   * true, wenn ein autorisierter Backend-Endpunkt existiert.
   * Im R0-Vertrag existieren KEINE VM-Aktions-Endpunkte — die
   * Aktion ist dann blockiert und wird als solche angezeigt
   * (docs/proposals/frontend-vm-actions.md).
   */
  endpointAvailable: boolean;
  busy?: boolean;
  onConfirm?: () => void;
}

/**
 * Bestaetigungsdialog fuer Verwaltungsaktionen (RBAC: operator+).
 * Wird NUR angezeigt, wenn die serverseitige Rolle es erlaubt;
 * die endgueltige Autorisierung erfolgt serverseitig (RBAC).
 */
export function ActionDialog({
  open,
  onOpenChange,
  action,
  resourceName,
  endpointAvailable,
  busy = false,
  onConfirm,
}: ActionDialogProps) {
  const label = ACTION_LABEL[action];

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`${label}: ${resourceName}`}
      description={
        endpointAvailable
          ? "Die Aktion wird ueber den autorisierten Backend-Endpunkt ausgefuehrt, auditiert und im Job-System protokolliert."
          : undefined
      }
    >
      {endpointAvailable ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm">
            Möchten Sie die Aktion <strong>{label.toLowerCase()}</strong> für{" "}
            <strong>{resourceName}</strong> ausführen?
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={busy}
            >
              Abbrechen
            </Button>
            <Button onClick={onConfirm} disabled={busy}>
              {busy && <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />}
              {busy ? "Wird ausgeführt…" : `${label} bestätigen`}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 text-sm font-medium text-status-degraded">
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            Aktion derzeit nicht verfügbar
          </div>
          <p className="text-xs text-muted-foreground">
            Im aktuellen API-Vertrag (R0, frozen) existieren keine Endpunkte
            für VM-/LXC-Aktionen. Verwaltungsaktionen dürfen ausschliesslich
            über autorisierte Backend-Endpunkte ausgelöst werden — es werden
            keine alternativen Wege erzeugt. Contract-Änderungsvorschlag:{" "}
            <span className="font-mono">
              docs/proposals/frontend-vm-actions.md
            </span>
            .
          </p>
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Schliessen
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
