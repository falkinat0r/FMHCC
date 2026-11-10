import { describe, expect, it } from "vitest";

import {
  FIXTURE_INTEGRATIONS,
  FIXTURE_RESOURCES,
  FIXTURE_USER,
  fixtureMetricSeries,
  pagedFixture,
} from "./fixtures";

/**
 * Fixture-Disziplin (AGENTS.md §7): alle Fixtures sind klar als
 * Demo-Fixtures gekennzeichnet und enthalten keine echten Daten.
 */
describe("Fixtures (Demo-Daten-Disziplin)", () => {
  it("benennen alle Ressourcen mit 'demo-'-Prefix (kein echtes Inventar)", () => {
    for (const resource of FIXTURE_RESOURCES) {
      expect(resource.external_id.startsWith("demo-")).toBe(true);
      expect(resource.name?.startsWith("demo-")).toBe(true);
    }
  });

  it("benennen alle Integrationen mit 'demo-'-Prefix", () => {
    for (const integration of FIXTURE_INTEGRATIONS) {
      expect(integration.integration_id.startsWith("demo-")).toBe(true);
      expect(integration.name).toContain("Fixture");
    }
  });

  it("ist der Fixture-Benutzer als Demo gekennzeichnet", () => {
    expect(FIXTURE_USER.username.startsWith("demo-")).toBe(true);
    expect(FIXTURE_USER.display_name).toContain("Fixture");
  });
});

describe("pagedFixture", () => {
  const items = Array.from({ length: 7 }, (_, i) => i);

  it("teilt korrekt auf (Seite 1 von 2 bei pageSize 5)", () => {
    const page = pagedFixture(items, 1, 5);
    expect(page.items).toEqual([0, 1, 2, 3, 4]);
    expect(page.total).toBe(7);
    expect(page.total_pages).toBe(2);
    expect(page.page).toBe(1);
  });

  it("liefert die letzte (kleinere) Seite", () => {
    const page = pagedFixture(items, 2, 5);
    expect(page.items).toEqual([5, 6]);
    expect(page.page).toBe(2);
  });

  it("clamped überzählige Seiten (keine undefinierten Items)", () => {
    const page = pagedFixture(items, 99, 5);
    expect(page.page).toBe(2);
    expect(page.items).toEqual([5, 6]);
  });

  it("liefert bei leerer Liste total 0 und 1 leere Seite", () => {
    const page = pagedFixture([], 1, 5);
    expect(page.items).toEqual([]);
    expect(page.total).toBe(0);
    expect(page.total_pages).toBe(1);
  });
});

describe("fixtureMetricSeries", () => {
  it("liefert die angefragte Anzahl Punkte", () => {
    expect(fixtureMetricSeries(60, 20, 10)).toHaveLength(10);
  });

  it("ist deterministisch (keine zufälligen Erfolgswerte)", () => {
    expect(fixtureMetricSeries(60, 20)).toEqual(fixtureMetricSeries(60, 20));
  });

  it("liefert physikalisch plausible Werte (>= 0, begrenzt)", () => {
    const points = fixtureMetricSeries(24 * 60, 55, 50);
    for (const point of points) {
      expect(point.value).toBeGreaterThanOrEqual(0);
      expect(point.value).toBeLessThanOrEqual(100);
      expect(Number.isNaN(Date.parse(point.ts))).toBe(false);
    }
  });
});
