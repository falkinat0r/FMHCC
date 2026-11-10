import { describe, expect, it } from "vitest";

import { ageInHours, formatCount, formatDateTime, timeAgo } from "./format";

const NOW = new Date("2026-11-10T12:00:00Z");

describe("timeAgo", () => {
  it("zeigt 'gerade eben' für wenige Sekunden", () => {
    expect(timeAgo("2026-11-10T11:59:50Z", NOW)).toBe("gerade eben");
  });

  it("zeigt Minuten", () => {
    expect(timeAgo("2026-11-10T11:55:00Z", NOW)).toBe("vor 5 min");
  });

  it("zeigt Stunden", () => {
    expect(timeAgo("2026-11-10T10:00:00Z", NOW)).toBe("vor 2 h");
  });

  it("zeigt Tage", () => {
    expect(timeAgo("2026-11-07T12:00:00Z", NOW)).toBe("vor 3 d");
  });

  it("zeigt 'n/v' bei fehlendem oder ungültigem Zeitstempel", () => {
    expect(timeAgo(null)).toBe("n/v");
    expect(timeAgo(undefined)).toBe("n/v");
    expect(timeAgo("definitiv-kein-datumsformat")).toBe("n/v");
  });
});

describe("formatDateTime", () => {
  it("formatiert UTC-Zeitstempel", () => {
    expect(formatDateTime("2026-11-10T12:00:00Z")).not.toBe("n/v");
  });

  it("zeigt 'n/v' ohne Zeitstempel", () => {
    expect(formatDateTime(null)).toBe("n/v");
    expect(formatDateTime("")).toBe("n/v");
  });
});

describe("ageInHours", () => {
  it("berechnet das Alter in Stunden", () => {
    expect(ageInHours("2026-11-10T09:00:00Z", NOW)).toBeCloseTo(3);
  });

  it("liefert null ohne Zeitstempel (=> 'n/v' in der UI)", () => {
    expect(ageInHours(null)).toBeNull();
    expect(ageInHours("unbekannt")).toBeNull();
  });

  it("klemmt negative Werte auf 0 (Zukunft ist kein Alter)", () => {
    expect(ageInHours("2026-11-10T13:00:00Z", NOW)).toBe(0);
  });
});

describe("formatCount", () => {
  it("formatiert Zahlen lokalisierungsgetreu", () => {
    expect(formatCount(1234)).toBe("1.234");
    expect(formatCount(0)).toBe("0");
  });

  it("zeigt 'n/v' für fehlende Werte — keine erfundenen Zahlen", () => {
    expect(formatCount(null)).toBe("n/v");
    expect(formatCount(undefined)).toBe("n/v");
  });
});
