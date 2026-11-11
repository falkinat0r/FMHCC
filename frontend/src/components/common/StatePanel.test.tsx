import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ApiRequestError } from "../../api/client";
import { StatePanel, describeApiError, queryStatePanel } from "./StatePanel";

describe("StatePanel", () => {
  it("zeigt im Ladezustand einen erkennbaren Fortschritt", () => {
    render(<StatePanel state="loading" />);
    expect(screen.getByLabelText("Wird geladen")).toBeInTheDocument();
    expect(screen.getByLabelText("Wird geladen")).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("zeigt Fehler mit Meldung, Request-ID und Retry-Option", async () => {
    const onRetry = vi.fn();
    render(
      <StatePanel
        state="error"
        error="Interner Serverfehler"
        requestId="req-abc"
        onRetry={onRetry}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Fehler bei der Datenabfrage");
    expect(alert).toHaveTextContent("Interner Serverfehler");
    expect(alert).toHaveTextContent("req-abc");
    fireEvent.click(screen.getByRole("button", { name: "Erneut versuchen" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("zeigt ohne onRetry keinen Retry-Button", () => {
    render(<StatePanel state="error" error="Fehler" />);
    expect(
      screen.queryByRole("button", { name: "Erneut versuchen" }),
    ).not.toBeInTheDocument();
  });

  it("zeigt den Leerzustand ehrlich an", () => {
    render(<StatePanel state="empty" emptyText="Keine Einträge vorhanden." />);
    expect(screen.getByText("Keine Einträge vorhanden.")).toBeInTheDocument();
  });

  it("unterscheidet 'nicht konfiguriert' von 'leer'", () => {
    render(
      <StatePanel
        state="not_configured"
        notConfiguredText="Quelle ist noch nicht eingerichtet."
      />,
    );
    expect(
      screen.getByText("Quelle ist noch nicht eingerichtet."),
    ).toBeInTheDocument();
  });
});

describe("describeApiError", () => {
  it("liest die Error-Envelope aus ApiRequestError", () => {
    const result = describeApiError(
      new ApiRequestError(403, "forbidden", "Zugriff verweigert", "req-1"),
    );
    expect(result).toEqual({
      message: "Zugriff verweigert",
      requestId: "req-1",
    });
  });

  it("verarbeitet allgemeine Error-Objekte", () => {
    const result = describeApiError(new Error("Etwas ist schief"));
    expect(result.message).toBe("Etwas ist schief");
    expect(result.requestId).toBe("");
  });

  it("fällt bei unbekannten Werten auf eine Standardmeldung zurück", () => {
    const result = describeApiError(42);
    expect(result.message).toBe("Unerwarteter Fehler");
    expect(result.requestId).toBe("");
  });
});

describe("queryStatePanel", () => {
  it("kapselt den Query-Fehler in ein StatePanel mit Request-ID", () => {
    render(
      queryStatePanel(
        new ApiRequestError(500, "internal", "Backendfehler", "req-9"),
      ),
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Backendfehler");
    expect(alert).toHaveTextContent("req-9");
  });
});
