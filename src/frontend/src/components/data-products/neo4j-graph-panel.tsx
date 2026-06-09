import { useState, useEffect, useCallback } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Background,
  Controls,
  MarkerType,
  Position,
  Handle,
  NodeProps,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import * as dagre from 'dagre';
import 'reactflow/dist/style.css';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, Database, Circle } from 'lucide-react';
import type { ManagementPort } from '@/types/data-product';

interface TopologyEdge {
  from_label: string;
  rel_type: string;
  to_label: string;
  count: number;
}

interface Neo4jSummary {
  connected: boolean;
  error: string | null;
  database: string;
  bolt_url: string;
  graph: {
    node_labels: string[];
    relationship_types: string[];
    node_counts: Record<string, number>;
    relationship_counts: Record<string, number>;
    total_nodes: number;
    total_relationships: number;
    topology: TopologyEdge[];
  };
  freshness: Record<string, string>;
}

interface Neo4jGraphPanelProps {
  managementPorts?: ManagementPort[];
}

// --- Custom node ---

interface KGNodeData {
  label: string;
  count: number;
  freshness?: string;
}

const KGNode = ({ data }: NodeProps<KGNodeData>) => (
  <div className="bg-background border-2 border-primary/50 rounded-xl px-4 py-2 shadow text-center min-w-[130px]">
    <Handle type="target" position={Position.Left} style={{ background: 'hsl(var(--primary))' }} />
    <div className="font-semibold text-sm leading-tight">{data.label}</div>
    <Badge variant="secondary" className="text-xs mt-1">{data.count}</Badge>
    {data.freshness && (
      <div className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{data.freshness}</div>
    )}
    <Handle type="source" position={Position.Right} style={{ background: 'hsl(var(--primary))' }} />
  </div>
);

const nodeTypes = { kgNode: KGNode };

// --- Dagre layout ---

const NODE_W = 150;
const NODE_H = 62;

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

function buildLayout(summary: Neo4jSummary): { nodes: Node[]; edges: Edge[] } {
  dagreGraph.setGraph({ rankdir: 'LR', ranksep: 90, nodesep: 50 });

  const nodes: Node[] = summary.graph.node_labels.map(label => ({
    id: label,
    type: 'kgNode',
    data: {
      label,
      count: summary.graph.node_counts[label] ?? 0,
      freshness: summary.freshness[label.toLowerCase()],
    },
    position: { x: 0, y: 0 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }));

  const edges: Edge[] = (summary.graph.topology ?? []).map((e, i) => ({
    id: `e-${i}`,
    source: e.from_label,
    target: e.to_label,
    label: e.rel_type,
    type: 'smoothstep',
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: { strokeWidth: 1.5 },
    labelStyle: { fontSize: 10, fontFamily: 'monospace' },
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 3,
  }));

  nodes.forEach(n => dagreGraph.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach(e => dagreGraph.setEdge(e.source, e.target));
  dagre.layout(dagreGraph);

  nodes.forEach(n => {
    const pos = dagreGraph.node(n.id);
    n.position = { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 };
  });

  return { nodes, edges };
}

// --- Panel ---

export default function Neo4jGraphPanel({ managementPorts }: Neo4jGraphPanelProps) {
  const [summary, setSummary] = useState<Neo4jSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const neo4jPort = managementPorts?.find(
    p => p.url && (p.url.includes('neo4j') || p.name?.toLowerCase().includes('neo4j'))
  );

  const fetchSummary = useCallback(async () => {
    if (!neo4jPort?.url) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(neo4jPort.url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Neo4jSummary = await res.json();
      setSummary(data);
      if (data.connected && data.graph.node_labels.length > 0) {
        const { nodes: n, edges: e } = buildLayout(data);
        setNodes(n);
        setEdges(e);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to fetch Neo4j summary');
    } finally {
      setLoading(false);
    }
  }, [neo4jPort?.url]);

  useEffect(() => {
    if (neo4jPort?.url) fetchSummary();
  }, [neo4jPort?.url]);

  if (!neo4jPort) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Database className="h-5 w-5" />
            Knowledge Graph Summary
          </span>
          <Button size="sm" variant="ghost" onClick={fetchSummary} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </CardTitle>
        <CardDescription>
          Live from <code className="text-xs bg-muted px-1 py-0.5 rounded">{neo4jPort.url?.split('?')[0]}</code>
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-3">
        {loading && !summary && (
          <div className="flex items-center gap-2 text-muted-foreground text-sm">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading graph metadata...
          </div>
        )}

        {error && <div className="text-sm text-destructive">{error}</div>}

        {summary && (
          <>
            {/* Stats row */}
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="flex items-center gap-1.5">
                <Circle className={`h-2 w-2 fill-current ${summary.connected ? 'text-green-500' : 'text-destructive'}`} />
                <span className="text-muted-foreground">{summary.database}</span>
              </span>
              <Badge variant="outline">{summary.graph.total_nodes} nodes</Badge>
              <Badge variant="outline">{summary.graph.total_relationships} relationships</Badge>
              {Object.entries(summary.freshness)
                .filter(([k]) => k !== 'id')
                .map(([feed, date]) => (
                  <span key={feed} className="text-xs text-muted-foreground">
                    <span className="font-medium">{feed}</span>: {date}
                  </span>
                ))}
            </div>

            {/* Graph canvas */}
            {nodes.length > 0 && (
              <div className="rounded-lg border bg-muted/20 overflow-hidden" style={{ height: 300 }}>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  nodeTypes={nodeTypes}
                  fitView
                  fitViewOptions={{ padding: 0.2 }}
                  proOptions={{ hideAttribution: true }}
                  nodesDraggable
                  nodesConnectable={false}
                  elementsSelectable={false}
                >
                  <Background gap={16} size={1} />
                  <Controls showInteractive={false} />
                </ReactFlow>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
