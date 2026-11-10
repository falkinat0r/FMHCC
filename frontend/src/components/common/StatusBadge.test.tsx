import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it.each(["healthy", "degraded", "down", "unknown", "not_configured"])(
    "zeigt den Contract-Zustand %s an",
    (status) => {
      render(<StatusBadge status={status} />);
      expect(screen.getByText(status)).toBeInTheDocument();
    },
  );

  it("fällt bei unbekanntem Wert auf 'unknown' zurück (keine Erfindung)", () => {
    render(<StatusBadge status="definitiv-neuer-wert" />);
    expect(screen.getByText("unknown")).toBeInTheDocument();
    expect(
      screen.queryByText("definitiv-neuer-wert"),
    ).not.toBeInTheDocument();
  });

  it("trägt den rohen Contract-Wert als data-status", () => {
    render(<StatusBadge status="down" />);
    const badge = screen.getByText("down").closest("[data-status]");
    expect(badge).toHaveAttribute("data-status", "down");
  });
});
