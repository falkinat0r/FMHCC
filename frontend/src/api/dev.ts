/**
 * Gekennzeichneter Entwicklungsmodus (DEV-FIXTURE).
 *
 * Nur erlaubt, wenn ein Backend-Endpunkt (noch) nicht existiert, um
 * die UI mit isolierten Test-Fixtures zu entwickeln
 * (docs/agent-reports/R1-frontend.md). Aktivierung:
 *
 *   - Build-Variable:  VITE_HCC_DEV_FIXTURE=true
 *   - oder URL-Parameter:  ?dev=fixture
 *
 * Solange der Modus aktiv ist, zeigt die UI dauerhaft einen
 * Banner "DEV-FIXTURE" — Fixtures werden niemals als Echtdaten
 * dargestellt (AGENTS.md Regel 7).
 */

export function isDevFixture(search: string = defaultSearch()): boolean {
  const envFlag = import.meta.env.VITE_HCC_DEV_FIXTURE;
  return envFlag === "true" || search.includes("dev=fixture");
}

function defaultSearch(): string {
  if (typeof window !== "undefined") return window.location.search;
  return "";
}
