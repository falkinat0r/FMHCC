import type { ResourceSource, ResourceStatus } from "../api/types";

/**
 * Fachliche Zustandsmodelle (frozen Contract, docs/api-contracts.md §1):
 * healthy | degraded | down | unknown | not_configured.
 *
 * Die Kennzeichnung ist in der UI verbindlich: jede Zustaend zeigt
 * genau diese funf Werte an, es gibt keine "Zwischenzustaeinde" und
 * keine erfundenen Erfolge.
 */

export interface StatusMeta {
  readonly label: string;
  readonly /** Tailwind-Klasse fuer Text */ textClass: string;
  readonly /** Tailwind-Klasse fuer Badge-Hintergrund (inkl. Textfarbe) */ badgeClass: string;
  readonly /** Punktfarbe fuer Topologie/Listen */ dotClass: string;
  readonly severity: number;
}

export const RESOURCE_STATUS: Record<ResourceStatus, StatusMeta> = {
  healthy: {
    label: "healthy",
    textClass: "text-status-healthy",
    badgeClass: "bg-status-healthy/15 text-status-healthy",
    dotClass: "bg-status-healthy",
    severity: 0,
  },
  degraded: {
    label: "degraded",
    textClass: "text-status-degraded",
    badgeClass: "bg-status-degraded/15 text-status-degraded",
    dotClass: "bg-status-degraded",
    severity: 1,
  },
  down: {
    label: "down",
    textClass: "text-status-down",
    badgeClass: "bg-status-down/15 text-status-down",
    dotClass: "bg-status-down",
    severity: 2,
  },
  unknown: {
    label: "unknown",
    textClass: "text-status-unknown",
    badgeClass: "bg-status-unknown/15 text-status-unknown",
    dotClass: "bg-status-unknown",
    severity: 3,
  },
  not_configured: {
    label: "not_configured",
    textClass: "text-status-not-configured",
    badgeClass: "bg-status-not-configured/15 text-status-not-configured",
    dotClass: "bg-status-not-configured",
    severity: 4,
  },
};

/**
 * Robust: bei unbekanntem Status-Wert (z. B. neuem Enum-Eintrag aus
 * einem naecheren Release) wird "unknown" angezeigt, nicht geraten.
 */
export function statusMeta(status: string): StatusMeta {
  return (
    RESOURCE_STATUS[status as ResourceStatus] ?? RESOURCE_STATUS.unknown
  );
}

/**
 * Herkunft/Evidenz (frozen): api | manual | inferred.
 * Fuer die Topologie: "api" = verifiziert, "manual" = manuell gepflegt,
 * "inferred" = abgeleitet (muss als vermutet gekennzeichnet sein).
 */
export interface SourceMeta {
  readonly label: string;
  readonly tooltip: string;
}

export const RESOURCE_SOURCE: Record<ResourceSource, SourceMeta> = {
  api: {
    label: "API (verifiziert)",
    tooltip: "Automatisch aus der Integrations-API erkannt",
  },
  manual: {
    label: "manuell",
    tooltip: "Manuell konfiguriert/gepflegt",
  },
  inferred: {
    label: "abgeleitet",
    tooltip: "Abgeleitet (vermutet), nicht verifiziert",
  },
};

export function sourceMeta(source: string): SourceMeta {
  return (
    RESOURCE_SOURCE[source as ResourceSource] ?? {
      label: source || "unbekannt",
      tooltip: "Unbekannte Herkunft",
    }
  );
}
