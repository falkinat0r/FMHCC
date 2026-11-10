import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  type Edge,
  type Node,
  type NodeChange,
  type NodeProps,
  type NodeTypes,
} from "reactflow";
import "reactflow/dist/style.css";

import {
  useResourceDetailsAll,
  useResources,
} from "../../api/query";
import {
  defaultLayout,
  edgesFromDetails,
  nodesFromResources,
  type NodeKind,
  type TopologyNode,
} from "./model";
import { PageHeader } from "../../components/common/PageHeader";
import { StatePanel, queryStatePanel } from "../../components/common/StatePanel";
import { StatusBadge } from "../../components/common/StatusBadge";
import { JsonView } from "../../components/common/JsonView";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import {
  Boxes,
  Cpu,
  Database,
  HardDrive,
  LayoutGrid,
  Server,
  Settings2,
} from "lucide-react";
import { cn } from "../../lib/cn";
import { sourceMeta, statusMeta } from "../../lib/status";
import { timeAgo } from "../../lib/format";

/**
 * Interaktive Topologie (React Flow).
 *
 * - Knoten: Ressourcen (1:1, keine Erfindungen)
 * - Kanten: Beziehungen aus dem Detail-Endpoint — Evidenz bleibt
 *   sichtbar: solide = API (verifiziert), gestrichelt = manuell,
 *   gepunktet = abgeleitet (vermutet).
 * - Persistente Positionen: LOKAL (localStorage) — im R0-Vertrag
 *   existiert kein Layout-Endpunkt (Proposal:
 *   docs/proposals/frontend-topology-bulk-relations.md).
 */
const POSITIONS_STORAGE_KEY = "hcc.topology.positions.v1";

const KIND_ICON: Record<NodeKind, typeof Server> = {
  host: Server,
  node: LayoutGrid,
  vm: Cpu,
  lxc: Boxes,
  container: Boxes,
  storage: HardDrive,
  service: Database,
  other: Settings2,
};

const KIND_BORDER: Record<NodeKind, string> = {
  host: "border-primary/70",
  node: "border-primary/40",
  vm: "border-border",
  lxc: "border-border",
  container: "border-border",
  storage: "border-status-degraded/40",
  service: "border-status-unknown/50",
  other: "border-border",
};

interface HccNodeData {
  label: string;
  kind: NodeKind;
  status: string;
  resourceType: string;
  integrationId: string;
  [key: string]: unknown;
}

function HccNodeComponent(props: NodeProps) {
  const data = props.data as HccNodeData;
  const Icon = KIND_ICON[data.kind];
  const meta = statusMeta(data.status);
  return (
    <div
      className={cn(
        "relative flex min-w-40 items-center gap-2 rounded-md border bg-card px-3 py-2 shadow",
        KIND_BORDER[data.kind],
      )}
    >
      {/*
       * Unsichtbare Handles: React Flow verankert Kanten an Handle-Elementen;
       * ohne Handles werden Kanten nicht gerendert (reactflow Error 008).
       * Die Topologie ist read-only, daher ist Verbinden deaktiviert
       * (nodesConnectable=false) und die Handles sind nur Verankerungspunkte.
       */}
      <Handle type="source" position={Position.Bottom} className="opacity-0" />
      <Handle type="target" position={Position.Top} className="opacity-0" />
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <div className="min-w-0">
        <p className="truncate text-xs font-medium leading-tight">{data.label}</p>
        <p className="text-[10px] leading-tight text-muted-foreground">
          {data.resourceType}
        </p>
      </div>
      <span
        aria-label={`Status ${data.status}`}
        className={cn("ml-1 h-2 w-2 shrink-0 rounded-full", meta.dotClass)}
      />
    </div>
  );
}

const nodeTypes: NodeTypes = { hcc: HccNodeComponent };

interface Positions {
  [nodeId: string]: { x: number; y: number };
}

function loadStoredPositions(): Positions {
  try {
    const raw = localStorage.getItem(POSITIONS_STORAGE_KEY);
    if (raw === null) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === "object" && parsed !== null) {
      return parsed as Positions;
    }
    return {};
  } catch {
    return {};
  }
}

function saveStoredPositions(positions: Positions): void {
  try {
    localStorage.setItem(POSITIONS_STORAGE_KEY, JSON.stringify(positions));
  } catch {
    // Speicher voll/blokiert: Positionen bleiben einfach nicht persistiert.
  }
}

export default function TopologyPage() {
  const navigate = useNavigate();
  const resources = useResources({ page: 1, pageSize: 200 });
  const details = useResourceDetailsAll(200);

  const [kindsEnabled, setKindsEnabled] = useState<Record<NodeKind, boolean>>({
    host: true,
    node: true,
    vm: true,
    lxc: true,
    container: true,
    storage: true,
    service: true,
    other: true,
  });
  const [showManual, setShowManual] = useState(true);
  const [showInferred, setShowInferred] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [positions, setPositions] = useState<Positions>({});
  const positionsRef = useRef<Positions>({});
  positionsRef.current = positions;

  const loadedAllResources = resources.data?.items.length === (resources.data?.total ?? 0);

  const allNodes = useMemo(
    () => nodesFromResources(resources.data?.items ?? []),
    [resources.data],
  );

  const basePositions = useMemo(() => defaultLayout(allNodes), [allNodes]);

  // Persistierte Positionen (localStorage) laden
  useEffect(() => {
    setPositions((prev) => ({ ...loadStoredPositions(), ...prev }));
  }, []);

  const { rfNodes, rfEdges, skippedEdges } = useMemo(() => {
    const visibleNodes = allNodes.filter(
      (n) => kindsEnabled[n.kind] === true,
    );
    const ids = new Set(visibleNodes.map((n) => n.id));
    const { edges: relationEdges, skipped } = edgesFromDetails(
      details.data?.details ?? [],
      ids,
    );
    const visibleEdges = relationEdges.filter((e) => {
      if (e.evidence === "manual") return showManual;
      if (e.evidence === "inferred") return showInferred;
      return true;
    });

    const nodes: Node[] = visibleNodes.map((node: TopologyNode) => {
      const pos = positions[node.id] ?? basePositions[node.id];
      return {
        id: node.id,
        type: "hcc",
        position: pos ?? { x: 0, y: 0 },
        data: {
          label: node.label,
          kind: node.kind,
          status: node.status,
          resourceType: node.resource.resource_type,
          integrationId: node.resource.integration_id,
        } satisfies HccNodeData,
      };
    });

    const edges: Edge[] = visibleEdges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.relationType,
      type: "smoothstep",
      style: {
        stroke:
          edge.evidence === "api"
            ? "#35b5a2"
            : edge.evidence === "manual"
              ? "#fbbf24"
              : "#94a3b8",
        strokeDasharray:
          edge.evidence === "manual"
            ? "6 4"
            : edge.evidence === "inferred"
              ? "2 4"
              : undefined,
        opacity: edge.evidence === "inferred" ? 0.55 : 0.9,
        strokeWidth: 1.5,
      },
      labelStyle: { fill: "#93a1b0", fontSize: 10 },
      labelBgStyle: { fill: "#151c24", fillOpacity: 0.85 },
    }));

    return { rfNodes: nodes, rfEdges: edges, skippedEdges: skipped };
  }, [allNodes, kindsEnabled, details.data, showManual, showInferred, positions, basePositions]);

  const selectedNode = allNodes.find((n) => n.id === selectedId) ?? null;

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      setSelectedId(node.id);
    },
    [],
  );

  const onNodesChange = useCallback((changes: NodeChange[]) => {
      // Positionen nur lokal aktualisieren (React Flow verwaltet sie);
      // Persistierung erfolgt im Drag-End.
      for (const change of changes) {
        if (change.type !== "position") continue;
        const position = change.position;
        if (position === undefined) continue;
        setPositions((prev) => ({
          ...prev,
          [change.id]: { x: position.x, y: position.y },
        }));
      }
    },
    [],
  );

  const onNodeDragStop = useCallback(
    (_: unknown, node: Node) => {
      const next = { ...positionsRef.current };
      next[node.id] = node.position;
      setPositions(next);
      saveStoredPositions(next);
    },
    [],
  );

  const resetLayout = useCallback(() => {
    const fresh = defaultLayout(allNodes);
    setPositions(fresh);
    saveStoredPositions(fresh);
  }, [allNodes]);

  if (resources.isLoading || (details.isLoading && resources.data !== undefined)) {
    return (
      <div>
        <PageHeader title="Topologie" description="Ressourcen- und Beziehungsübersicht" />
        <StatePanel state="loading" rows={8} />
      </div>
    );
  }

  if (resources.error !== null || details.error !== null) {
    return (
      <div>
        <PageHeader title="Topologie" description="Ressourcen- und Beziehungsübersicht" />
        {queryStatePanel(
          resources.error ?? details.error,
          () => {
            void resources.refetch();
            void details.refetch();
          },
        )}
      </div>
    );
  }

  const presentKinds = Array.from(new Set(allNodes.map((n) => n.kind)));
  const hasData = allNodes.length > 0;

  return (
    <div>
      <PageHeader
        title="Topologie"
        description="Interaktive Ansicht: Hosts, Nodes, VMs/LXC, Container, Storage und Dienste. Kanten nur aus dokumentierten Beziehungen — keine erfundenen Verbindungen."
        actions={
          <Button variant="outline" size="sm" onClick={resetLayout} disabled={!hasData}>
            Layout zurücksetzen
          </Button>
        }
      />

      {!hasData ? (
        <StatePanel
          state="empty"
          emptyText="Keine Ressourcen im Inventar — Topologie ist leer (keine Fixtures)."
        />
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          <Card className="min-w-0 flex-1">
            <CardContent className="p-0">
              <div className="h-[540px] w-full">
                <ReactFlow
                  nodes={rfNodes}
                  edges={rfEdges}
                  nodeTypes={nodeTypes}
                  onNodeClick={onNodeClick}
                  onNodesChange={onNodesChange}
                  onNodeDragStop={onNodeDragStop}
                  onConnect={() => {
                    // Manuell gezogene Kanten werden NICHT akzeptiert —
                    // Beziehungen kommen ausschliesslich aus dem Backend.
                  }}
                  fitView
                  minZoom={0.2}
                  maxZoom={2.5}
                  nodesConnectable={false}
                >
                  <Background variant={BackgroundVariant.Dots} gap={24} color="#263241" />
                  <Controls position="bottom-left" />
                  <MiniMap
                    position="bottom-right"
                    nodeColor={() => "#35b5a2"}
                    maskColor="rgba(0,0,0,0.6)"
                  />
                </ReactFlow>
              </div>
            </CardContent>
          </Card>

          <div className="flex w-full flex-col gap-4 lg:w-72">
            <Card>
              <CardHeader>
                <CardTitle>Filter</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-xs">
                <p className="font-medium text-muted-foreground">Knotenklassen</p>
                <div className="flex flex-wrap gap-x-3 gap-y-1.5">
                  {presentKinds.map((kind) => (
                    <label key={kind} className="flex items-center gap-1.5">
                      <input
                        type="checkbox"
                        checked={kindsEnabled[kind] === true}
                        onChange={(e) =>
                          setKindsEnabled((prev) => ({
                            ...prev,
                            [kind]: e.target.checked,
                          }))
                        }
                        className="h-3.5 w-3.5 accent-[var(--color-primary)]"
                      />
                      {kind}
                    </label>
                  ))}
                </div>
                <SeparatorLike />
                <p className="font-medium text-muted-foreground">Beziehungen (Evidenz)</p>
                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked
                    onChange={() => undefined}
                    disabled
                    className="h-3.5 w-3.5 accent-[var(--color-primary)]"
                  />
                  <span className="flex items-center gap-1.5">
                    <span className="h-0.5 w-6 bg-primary" aria-hidden="true" />
                    API (verifiziert)
                  </span>
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={showManual}
                    onChange={(e) => setShowManual(e.target.checked)}
                    className="h-3.5 w-3.5 accent-[var(--color-primary)]"
                  />
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-0.5 w-6 border-t-2 border-dashed border-status-degraded"
                      aria-hidden="true"
                    />
                    manuell konfiguriert
                  </span>
                </label>
                <label className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    checked={showInferred}
                    onChange={(e) => setShowInferred(e.target.checked)}
                    className="h-3.5 w-3.5 accent-[var(--color-primary)]"
                  />
                  <span className="flex items-center gap-1.5">
                    <span
                      className="h-0.5 w-6 border-t-2 border-dotted border-status-unknown"
                      aria-hidden="true"
                    />
                    abgeleitet (vermutet)
                  </span>
                </label>
                {skippedEdges > 0 && (
                  <p className="mt-1 text-[10px] text-status-degraded">
                    {skippedEdges} Beziehung(en) enden außerhalb der
                    angezeigten Knoten und werden nicht gezeichnet.
                  </p>
                )}
                {details.data !== undefined && details.data.failed > 0 && (
                  <p className="mt-1 text-[10px] text-status-degraded">
                    {details.data.failed} Detail-Abruf(e) fehlgeschlagen —
                    deren Beziehungen fehlen in dieser Ansicht.
                  </p>
                )}
                {loadedAllResources !== true && (
                  <p className="mt-1 text-[10px] text-muted-foreground">
                    Ansicht limitiert auf die ersten 200 Ressourcen
                    (Total: {resources.data?.total ?? "?"}). Bulk-Endpunkt
                    siehe Proposal.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card className="min-h-40">
              <CardHeader>
                <CardTitle>Details</CardTitle>
              </CardHeader>
              <CardContent>
                {selectedNode === null ? (
                  <p className="text-xs text-muted-foreground">
                    Knoten auswählen für Details.
                  </p>
                ) : (
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-sm font-medium">
                        {selectedNode.label}
                      </p>
                      <StatusBadge status={selectedNode.status} />
                    </div>
                    <p className="text-[11px] text-muted-foreground">
                      {selectedNode.resource.resource_type} ·{" "}
                      {selectedNode.resource.integration_id}
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Quelle: {sourceMeta(selectedNode.resource.source).label}
                      {" · "}
                      beobachtet {timeAgo(selectedNode.resource.observed_at)}
                    </p>
                    <div className="rounded border border-border bg-muted/30 p-2 text-[11px]">
                      Position persistiert lokal (Browser) — kein
                      Layout-Endpunkt im R0-Vertrag.
                    </div>
                    <JsonView data={selectedNode.resource.payload} />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => navigate(`/resources/${selectedNode.id}`)}
                    >
                      Vollständige Details öffnen
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function SeparatorLike() {
  return <hr className="my-1 border-border" />;
}
