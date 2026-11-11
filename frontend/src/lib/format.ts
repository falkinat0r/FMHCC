/**
 * Zeit- und Formatierungshelfer.
 *
 * Alle Zeitstempel aus der API sind UTC (ISO-8601, frozen Contract).
 * Die Anzeige nutzt die Browser-Lokalisierung, das Format ist
 * deterministisch testbar (de-DE-Fallback).
 */

/** Formatiert einen UTC-ISO-Zeitstempel als lokales Datum/Zeit. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/v";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "n/v";
  return new Intl.DateTimeFormat("de-DE", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

/** Formatiert einen UTC-ISO-Zeitstempel nur als Uhrzeit. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "n/v";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "n/v";
  return new Intl.DateTimeFormat("de-DE", { timeStyle: "medium" }).format(date);
}

/**
 * Relativer Zeitabstand ("vor 3 min"). `now` injizierbar für Tests.
 * Gibt "n/v" zurueck, wenn der Zeitstempel fehlt/ungueltig ist —
 * niemals erfundene Werte.
 */
export function timeAgo(
  iso: string | null | undefined,
  now: Date = new Date(),
): string {
  if (!iso) return "n/v";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "n/v";
  const seconds = Math.round((now.getTime() - date.getTime()) / 1000);
  if (seconds < 0) return formatDateTime(iso);
  if (seconds < 60) return "gerade eben";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `vor ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} h`;
  const days = Math.floor(hours / 24);
  return `vor ${days} d`;
}

/**
 * Datenalter (Staleness) in Stunden, z. B. fuer "Quelle: vor 1,4 h".
 * null, wenn kein Zeitstempel vorhanden ist (=> "n/v").
 */
export function ageInHours(
  iso: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const hours = (now.getTime() - date.getTime()) / 3_600_000;
  return hours < 0 ? 0 : hours;
}

/** Zahlengruesse in menschenlesbare Form (1234 -> "1,23 k"). */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "n/v";
  return new Intl.NumberFormat("de-DE").format(value);
}
