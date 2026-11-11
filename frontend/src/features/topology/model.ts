import type {
  ResourceDetailOut,
  ResourceOut,
} from "../../api/types";

/**
 * Topologie-Datenmodell (R2-Foerderung, gegen eingefrorene
 * Inventar-Contracts).
 *
 * REGLEN:
 * - Knoten entstehen 1:1 aus Ressourcen (GET /resources) — keine
 *   erfundenen Knoten.
 * - Kanten entstehen 1:1 aus Beziehungen (relations in
 *   GET /resources/{id}) — keine erfundenen Verbindungen.
 *   Beziehungen ohne beides Endpunkte in der geladenen Menge
 *   werden NICHT gezeichnet, sondern gezuehlt (skipped).
 * - Evidenz wird erhalten: "api" = verifiziert, "manual" = manuell
 *   konfiguriert, "inferred" = abgeleitet/vermutet (visuell getrennt).
 */

export type NodeKind =
  | "host"
  | "node"
  | "vm"
  | "lxc"
  | "container"
  | "storage"
  | "service"
  | "other";

/** Abbildung der frozen ResourceType-Enum auf visuelle Knotenklassen. */
export function kindForType(resourceType: string): NodeKind {
  switch (resourceType) {
    case "host":
      return "host";
    case "node":
      return "node";
    case "vm":
      return "vm";
    case "lxc":
      return "lxc";
    case "container":
      return "container";
    case "pool":
    case "dataset":
      return "storage";
    case "tailnet_node":
    case "dns_stats":
    case "dashboard":
      return "service";
    case "other":
      return "other";
    default:
      // Unbekannter Typ (neuere Releases): als "other" zeigen, nicht raten.
      return "other";
  }
}

export interface TopologyNode {
  readonly id: string;
  readonly kind: NodeKind;
  readonly label: string;
  readonly status: string;
  readonly resource: ResourceOut;
}

export interface TopologyEdge {
  readonly id: string;
  readonly source: string;
  readonly target: string;
  readonly relationType: string;
  /** Evidenz aus dem Contract: api | manual | inferred */
  readonly evidence: "api" | "manual" | "inferred";
  readonly note: string | null;
}

export function nodesFromResources(
  resources: readonly ResourceOut[],
): TopologyNode[] {
  return resources.map((resource) => ({
    id: resource.id,
    kind: kindForType(resource.resource_type),
    label: resource.name ?? resource.external_id,
    status: resource.status,
    resource,
  }));
}

export interface EdgeBuildResult {
  readonly edges: TopologyEdge[];
  /** Beziehungen, die wegen fehlendem Endpunkt in der Ansicht nicht gezeichnet wurden. */
  readonly skipped: number;
}

/**
 * Kanten aus Relations — dedupliziert (Source,Target,Typ), Evidenz
 * bleibt erhalten. Nur Beziehungen mit beiden Endpunkten in
 * `nodeIds` werden verwendet.
 */
export function edgesFromDetails(
  details: readonly ResourceDetailOut[],
  nodeIds: ReadonlySet<string>,
): EdgeBuildResult {
  const seen = new Set<string>();
  const edges: TopologyEdge[] = [];
  let skipped = 0;

  for (const detail of details) {
    for (const relation of detail.relations) {
      const key = `${relation.source_resource_id}->${relation.target_resource_id}:${relation.relation_type}`;
      if (seen.has(key)) continue;
      seen.add(key);

      if (
        !nodeIds.has(relation.source_resource_id) ||
        !nodeIds.has(relation.target_resource_id)
      ) {
        skipped += 1;
        continue;
      }

      edges.push({
        id: relation.id,
        source: relation.source_resource_id,
        target: relation.target_resource_id,
        relationType: relation.relation_type,
        evidence: relation.evidence,
        note: relation.note ?? null,
      });
    }
  }

  return { edges, skipped };
}

/* ------------------------------------------------------------------ */
/* Layout (deterministisch)                                            */
/* ------------------------------------------------------------------ */

const ROW_BY_KIND: Record<NodeKind, number> = {
  host: 0,
  node: 1,
  vm: 2,
  lxc: 2,
  container: 2,
  storage: 3,
  service: 4,
  other: 5,
};

const X_STEP = 190;
const Y_STEP = 150;
const X_START = 40;
const Y_START = 40;

/**
 * Deterministisches Grundlayout: Zeilen je Knotenklasse (Hosts oben,
 * dann Nodes, dann Workloads, Storage, Dienste). Innerhalb einer
 * Zeile alphabetisch nach Label — stabil zwischen Ladevorgängen.
 */
export function defaultLayout(
  nodes: readonly TopologyNode[],
): Record<string, { x: number; y: number }> {
  const rows = new Map<number, TopologyNode[]>();
  for (const node of nodes) {
    const row = ROW_BY_KIND[node.kind];
    const list = rows.get(row) ?? [];
    list.push(node);
    rows.set(row, list);
  }

  const positions: Record<string, { x: number; y: number }> = {};
  for (const [row, list] of rows) {
    list.sort((a, b) => a.label.localeCompare(b.label));
    list.forEach((node, idx) => {
      positions[node.id] = {
        x: X_START + idx * X_STEP,
        y: Y_START + row * Y_STEP,
      };
    });
  }
  return positions;
}
