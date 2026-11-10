import { describe, expect, it } from "vitest";

import {
  defaultLayout,
  edgesFromDetails,
  kindForType,
  nodesFromResources,
  type TopologyNode,
} from "./model";
import {
  FIXTURE_RESOURCE_DETAILS,
  FIXTURE_RESOURCES,
} from "../../api/fixtures";
import type { ResourceDetailOut, ResourceOut } from "../../api/types";

/** Test-Doppel: gültiges ResourceOut, Felder injizierbar. */
function makeResource(overrides: Partial<ResourceOut> = {}): ResourceOut {
  const base = FIXTURE_RESOURCES[0]!;
  return { ...base, ...overrides };
}

function makeRelation(
  overrides: Partial<ResourceDetailOut["relations"][number]> = {},
): ResourceDetailOut["relations"][number] {
  return {
    id: "rel-1",
    source_resource_id: "res-a",
    target_resource_id: "res-b",
    relation_type: "runs",
    evidence: "api",
    note: null,
    observed_at: "2026-11-10T12:00:00+00:00",
    source_name: "a",
    target_name: "b",
    ...overrides,
  };
}

function makeDetail(
  id: string,
  relations: ResourceDetailOut["relations"],
): ResourceDetailOut {
  return { ...makeResource({ id }), relations };
}

describe("kindForType", () => {
  it("mappt alle frozen ResourceType-Werte auf Knotenklassen", () => {
    expect(kindForType("host")).toBe("host");
    expect(kindForType("node")).toBe("node");
    expect(kindForType("vm")).toBe("vm");
    expect(kindForType("lxc")).toBe("lxc");
    expect(kindForType("container")).toBe("container");
    expect(kindForType("pool")).toBe("storage");
    expect(kindForType("dataset")).toBe("storage");
    expect(kindForType("tailnet_node")).toBe("service");
    expect(kindForType("dns_stats")).toBe("service");
    expect(kindForType("dashboard")).toBe("service");
    expect(kindForType("other")).toBe("other");
  });

  it("fällt bei unbekannten Typen auf 'other' zurück (nicht raten)", () => {
    expect(kindForType("future_resource_type")).toBe("other");
    expect(kindForType("")).toBe("other");
  });
});

describe("nodesFromResources", () => {
  it("bildet Knoten 1:1 aus Ressourcen — keine erfundenen Knoten", () => {
    const nodes = nodesFromResources(FIXTURE_RESOURCES);
    expect(nodes).toHaveLength(FIXTURE_RESOURCES.length);
    for (const resource of FIXTURE_RESOURCES) {
      expect(nodes.map((n) => n.id)).toContain(resource.id);
    }
  });

  it("übernimmt Status und Typ aus dem Contract", () => {
    const nodes = nodesFromResources([
      makeResource({ id: "res-x", resource_type: "vm", status: "degraded" }),
    ]);
    expect(nodes[0]).toMatchObject({ id: "res-x", kind: "vm", status: "degraded" });
  });

  it("nutzt Name, sonst external_id als Label", () => {
    const named = nodesFromResources([
      makeResource({ id: "res-1", name: "Meine VM" }),
    ]);
    expect(named[0]?.label).toBe("Meine VM");

    const unnamed = nodesFromResources([
      makeResource({ id: "res-2", name: null, external_id: "vm-ext-42" }),
    ]);
    expect(unnamed[0]?.label).toBe("vm-ext-42");
  });
});

describe("edgesFromDetails", () => {
  const allIds = new Set(FIXTURE_RESOURCES.map((r) => r.id));
  const allDetails = Object.values(FIXTURE_RESOURCE_DETAILS);

  it("bildet Kanten 1:1 aus dokumentierten Beziehungen", () => {
    const { edges } = edgesFromDetails(allDetails, allIds);
    const expected = allDetails.reduce(
      (sum, d) => sum + d.relations.length,
      0,
    );
    expect(edges).toHaveLength(expected);
  });

  it("erhält die Evidenz (api / manual / inferred)", () => {
    const { edges } = edgesFromDetails(allDetails, allIds);
    const evidences = new Set(edges.map((e) => e.evidence));
    expect(evidences).toContain("api");
    expect(evidences).toContain("manual");
    expect(evidences).toContain("inferred");
  });

  it("zeigt nur Kanten, deren beide Endpunkte in der Ansicht sind", () => {
    // Nur der Host sichtbar: seine Beziehung zum Node darf nicht gezeichnet werden
    const { edges, skipped } = edgesFromDetails(
      [makeDetail("res-a", [makeRelation()])],
      new Set(["res-a"]),
    );
    expect(edges).toHaveLength(0);
    expect(skipped).toBe(1);
  });

  it("zählt übersprungene Beziehungen, statt sie zu erfinden", () => {
    const details = [
      makeDetail("res-a", [
        makeRelation({ id: "r1", source_resource_id: "res-a", target_resource_id: "res-b" }),
        makeRelation({ id: "r2", source_resource_id: "res-a", target_resource_id: "res-outside" }),
        makeRelation({ id: "r3", source_resource_id: "res-a", target_resource_id: "res-c", relation_type: "contains" }),
      ]),
    ];
    const { edges, skipped } = edgesFromDetails(
      details,
      new Set(["res-a", "res-b", "res-c"]),
    );
    expect(edges.map((e) => e.id).sort()).toEqual(["r1", "r3"]);
    expect(skipped).toBe(1);
  });

  it("dedupliziert identische Beziehungen (Source, Target, Typ)", () => {
    const relation = makeRelation({
      source_resource_id: "res-a",
      target_resource_id: "res-b",
    });
    const details = [
      makeDetail("res-a", [relation]),
      makeDetail("res-b", [relation]),
    ];
    const { edges, skipped } = edgesFromDetails(
      details,
      new Set(["res-a", "res-b"]),
    );
    expect(edges).toHaveLength(1);
    expect(skipped).toBe(0);
  });

  it("enthält ausschließlich Endpunkte aus der geladenen Menge (Evidenz-Regel)", () => {
    const ids = new Set(["res-a", "res-b", "res-c"]);
    const { edges } = edgesFromDetails(
      [
        makeDetail("res-a", [
          makeRelation({
            source_resource_id: "res-a",
            target_resource_id: "res-b",
          }),
        ]),
      ],
      ids,
    );
    for (const edge of edges) {
      expect(ids.has(edge.source)).toBe(true);
      expect(ids.has(edge.target)).toBe(true);
    }
  });
});

describe("defaultLayout", () => {
  it("ist deterministisch (stabil zwischen Ladevorgängen)", () => {
    const nodes = nodesFromResources(FIXTURE_RESOURCES);
    expect(defaultLayout(nodes)).toEqual(defaultLayout(nodes));
  });

  it("ordnet Zeilen nach Knotenklasse (Hosts oben, Storage/Services darunter)", () => {
    const nodes: TopologyNode[] = [
      {
        id: "svc-1",
        kind: "service",
        label: "service",
        status: "healthy",
        resource: makeResource({ id: "svc-1", resource_type: "dns_stats" }),
      },
      {
        id: "vm-1",
        kind: "vm",
        label: "vm",
        status: "healthy",
        resource: makeResource({ id: "vm-1", resource_type: "vm" }),
      },
      {
        id: "host-1",
        kind: "host",
        label: "host",
        status: "healthy",
        resource: makeResource({ id: "host-1", resource_type: "host" }),
      },
    ];
    const positions = defaultLayout(nodes);
    expect(positions["host-1"]?.y).toBeLessThan(positions["vm-1"]?.y ?? Infinity);
    expect(positions["vm-1"]?.y).toBeLessThan(positions["svc-1"]?.y ?? Infinity);
  });

  it("sortiert innerhalb einer Zeile alphabetisch nach Label", () => {
    const nodes = nodesFromResources([
      makeResource({ id: "res-b", name: "b-vm" }),
      makeResource({ id: "res-a", name: "a-vm" }),
    ]);
    const positions = defaultLayout(nodes);
    expect(positions["res-a"]?.x).toBeLessThan(positions["res-b"]?.x ?? Infinity);
    // Gleiche Zeile (beide vm)
    expect(positions["res-a"]?.y).toBe(positions["res-b"]?.y);
  });

  it("liefert für jede Ressource genau eine Position", () => {
    const nodes = nodesFromResources(FIXTURE_RESOURCES);
    const positions = defaultLayout(nodes);
    expect(Object.keys(positions)).toHaveLength(nodes.length);
    for (const node of nodes) {
      expect(positions[node.id]).toBeDefined();
    }
  });
});
