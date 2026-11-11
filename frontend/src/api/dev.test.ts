import { afterEach, describe, expect, it, vi } from "vitest";

import { isDevFixture } from "./dev";

/**
 * DEV-FIXTURE-Modus (AGENTS.md §7): Fixtures sind nur im explizit
 * gekennzeichneten Modus aktiv und werden niemals als Echtdaten
 * dargestellt. Die Prüfung läuft über URL-Parameter oder Build-Variable.
 */
describe("isDevFixture", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("ist ohne Parameter und ohne Env-Variable deaktiviert", () => {
    expect(isDevFixture("")).toBe(false);
    expect(isDevFixture("?role=viewer")).toBe(false);
    expect(isDevFixture("?dev=nein")).toBe(false);
  });

  it("wird durch den URL-Parameter ?dev=fixture aktiviert", () => {
    expect(isDevFixture("?dev=fixture")).toBe(true);
    expect(isDevFixture("?role=viewer&dev=fixture")).toBe(true);
    expect(isDevFixture("?dev=fixture&role=admin")).toBe(true);
  });

  it("wird durch die Build-Variable VITE_HCC_DEV_FIXTURE=true aktiviert", () => {
    vi.stubEnv("VITE_HCC_DEV_FIXTURE", "true");
    expect(isDevFixture("")).toBe(true);
  });

  it("bleibt ohne Variable deaktiviert", () => {
    vi.stubEnv("VITE_HCC_DEV_FIXTURE", "false");
    expect(isDevFixture("")).toBe(false);
  });
});
