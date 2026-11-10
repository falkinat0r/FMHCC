import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ActionDialog } from "./ActionDialog";

function renderDialog(props: Partial<Parameters<typeof ActionDialog>[0]> = {}) {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    action: "start" as const,
    resourceName: "demo-vm-101",
    endpointAvailable: false,
  };
  return render(<ActionDialog {...defaultProps} {...props} />);
}

describe("ActionDialog", () => {
  it("rendert bei open=false nichts", () => {
    renderDialog({ open: false });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("zeigt blockierte Aktionen ohne Endpunkt an (R0-Vertrag: keine VM-Aktionen)", () => {
    renderDialog({ endpointAvailable: false });

    expect(screen.getByRole("dialog")).toHaveAccessibleName(
      "Starten: demo-vm-101",
    );
    expect(
      screen.getByText("Aktion derzeit nicht verfügbar"),
    ).toBeInTheDocument();
    // Verweis auf das Contract-Proposal
    expect(
      screen.getByText(/docs\/proposals\/frontend-vm-actions\.md/),
    ).toBeInTheDocument();

    // Kein ausführender Bestätigungs-Button
    expect(
      screen.queryByRole("button", { name: "Starten bestätigen" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Schliessen" })).toBeInTheDocument();
  });

  it("ruft beim Schließen onOpenChange(false) auf", () => {
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange, endpointAvailable: false });
    fireEvent.click(screen.getByRole("button", { name: "Schliessen" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("bietet mit Endpunkt die Bestätigung und führt die Aktion aus", () => {
    const onConfirm = vi.fn();
    renderDialog({ endpointAvailable: true, onConfirm });

    const confirm = screen.getByRole("button", { name: "Starten bestätigen" });
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("zeigt die Aktion im Titel", () => {
    renderDialog({ action: "reboot" });
    expect(screen.getByRole("dialog")).toHaveAccessibleName(
      "Neu starten: demo-vm-101",
    );
  });
});
