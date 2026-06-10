import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
// @ts-expect-error - react-cytoscapejs doesn't have type declarations
import CytoscapeComponent from 'react-cytoscapejs';
import type { Core, ElementDefinition, LayoutOptions } from 'cytoscape';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Loader2, RefreshCw, Database, Circle, ZoomIn, ZoomOut, Maximize, RotateCcw, Expand } from 'lucide-react';
import type { ManagementPort } from '@/types/data-product';

// --- Types ---

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

type LayoutType = 'breadthfirst' | 'circle' | 'cose' | 'concentric';

// --- Constants ---

const NODE_COLORS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#DDA0DD',
  '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8B500', '#77DD77',
  '#FFB347', '#AEC6CF',
];

// --- Helpers ---

function buildElements(summary: Neo4jSummary): ElementDefinition[] {
  const elements: ElementDefinition[] = [];

  summary.graph.node_labels.forEach((label, i) => {
    const count = summary.graph.node_counts[label] ?? 0;
    const freshness = summary.freshness[label.toLowerCase()];
    elements.push({
      data: {
        id: label,
        label,
        count,
        freshness,
        color: NODE_COLORS[i % NODE_COLORS.length],
        subtitle: freshness ? `${count.toLocaleString()} · ${freshness}` : count.toLocaleString(),
      },
      classes: 'kg-node',
    });
  });

  (summary.graph.topology ?? []).forEach((edge, i) => {
    const label = edge.rel_type.replace(/_/g, ' ');
    elements.push({
      data: {
        id: `e${i}-${edge.from_label}-${edge.rel_type}-${edge.to_label}`,
        source: edge.from_label,
        target: edge.to_label,
        label,
        rawLabel: edge.rel_type,
        count: edge.count,
      },
      classes: 'kg-edge',
    });
  });

  return elements;
}

function getLayoutConfig(name: LayoutType): LayoutOptions {
  const base = { fit: true, padding: 60, animate: true, animationDuration: 400 };
  switch (name) {
    case 'breadthfirst':
      return { name: 'breadthfirst', ...base, directed: true, spacingFactor: 2.0, avoidOverlap: true, maximal: false };
    case 'circle':
      return { name: 'circle', ...base, avoidOverlap: true, spacingFactor: 2.2 };
    case 'cose':
      return {
        name: 'cose', ...base,
        idealEdgeLength: () => 140,
        nodeRepulsion: () => 600000,
        gravity: 80,
        numIter: 500,
        initialTemp: 200,
        coolingFactor: 0.95,
        minTemp: 1.0,
        randomize: false,
      };
    case 'concentric':
      return {
        name: 'concentric', ...base,
        avoidOverlap: true, minNodeSpacing: 30,
        concentric: (node: any) => node.degree(),
        levelWidth: () => 2,
      };
    default:
      return { name: 'breadthfirst', ...base };
  }
}

function buildStylesheet(isDarkMode: boolean): any[] {
  const textColor = isDarkMode ? '#f1f5f9' : '#1f2937';
  const textOutline = isDarkMode ? 'rgba(0,0,0,0.85)' : 'rgba(255,255,255,0.9)';
  const edgeColor = isDarkMode ? '#71717a' : '#64748b';
  const edgeLabelColor = isDarkMode ? '#a1a1aa' : '#6b7280';

  return [
    {
      selector: 'node.kg-node',
      style: {
        shape: 'ellipse',
        width: 52,
        height: 52,
        'background-color': 'data(color)',
        'border-width': 2.5,
        'border-color': isDarkMode ? 'rgba(20,20,20,0.85)' : 'rgba(255,255,255,0.95)',
        label: 'data(label)',
        'font-family': 'Inter, -apple-system, BlinkMacSystemFont, sans-serif',
        'font-size': 12,
        'font-weight': 600,
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 7,
        color: textColor,
        'text-outline-width': 2.5,
        'text-outline-color': textOutline,
      },
    },
    {
      selector: 'node.kg-node.hover',
      style: {
        width: 66,
        height: 66,
        'border-width': 3.5,
        'font-size': 14,
        'font-weight': 700,
        'z-index': 999,
      },
    },
    {
      selector: 'node.kg-node:selected',
      style: {
        width: 70,
        height: 70,
        'border-width': 4,
        'border-color': '#FFD700',
        'font-size': 14,
        'font-weight': 700,
      },
    },
    {
      selector: 'edge.kg-edge',
      style: {
        width: 2,
        'line-color': edgeColor,
        'target-arrow-color': edgeColor,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 1.0,
        'curve-style': 'bezier',
        opacity: 0.65,
        label: 'data(label)',
        'font-size': 10,
        'font-family': 'ui-monospace, SFMono-Regular, Menlo, monospace',
        color: edgeLabelColor,
        'text-outline-width': 2,
        'text-outline-color': textOutline,
        'text-rotation': 'autorotate',
        'text-margin-y': -9,
      },
    },
    {
      selector: 'edge.kg-edge.hover',
      style: {
        width: 3,
        opacity: 1,
        'line-color': '#FFD700',
        'target-arrow-color': '#FFD700',
        color: textColor,
      },
    },
  ];
}

// --- Sub-components ---

interface GraphControlsProps {
  layout: LayoutType;
  onLayoutChange: (l: LayoutType) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onReset: () => void;
  onFullscreen?: () => void;
  nodeCount: number;
  edgeCount: number;
}

function GraphControls({
  layout, onLayoutChange, onZoomIn, onZoomOut, onFit, onReset, onFullscreen, nodeCount, edgeCount,
}: GraphControlsProps) {
  return (
    <div className="px-3 py-1.5 border-b flex items-center justify-between bg-muted/20">
      <div className="flex items-center gap-2">
        <Select value={layout} onValueChange={(v) => onLayoutChange(v as LayoutType)}>
          <SelectTrigger className="w-[148px] h-7 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="breadthfirst">Hierarchical</SelectItem>
            <SelectItem value="circle">Circular</SelectItem>
            <SelectItem value="cose">Force-Directed</SelectItem>
            <SelectItem value="concentric">Concentric</SelectItem>
          </SelectContent>
        </Select>
        <span className="text-xs text-muted-foreground">
          {nodeCount} nodes · {edgeCount} edges
        </span>
      </div>
      <div className="flex items-center gap-0.5">
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onZoomOut} title="Zoom Out">
          <ZoomOut className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onZoomIn} title="Zoom In">
          <ZoomIn className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onFit} title="Fit to View">
          <Maximize className="h-3.5 w-3.5" />
        </Button>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onReset} title="Reset Layout">
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
        {onFullscreen && (
          <>
            <div className="w-px h-4 bg-border mx-0.5" />
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onFullscreen} title="Fullscreen">
              <Expand className="h-3.5 w-3.5" />
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

// --- Main component ---

export default function Neo4jGraphPanel({ managementPorts }: Neo4jGraphPanelProps) {
  const [summary, setSummary] = useState<Neo4jSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [layout, setLayout] = useState<LayoutType>('breadthfirst');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const cyRef = useRef<Core | null>(null);
  const fullCyRef = useRef<Core | null>(null);
  const layoutRef = useRef<any>(null);

  const neo4jPort = managementPorts?.find(
    p => p.url && (p.url.includes('neo4j') || p.name?.toLowerCase().includes('neo4j'))
  );

  // Track dark mode
  useEffect(() => {
    const check = () => setIsDarkMode(document.documentElement.classList.contains('dark'));
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => observer.disconnect();
  }, []);

  const fetchSummary = useCallback(async () => {
    if (!neo4jPort?.url) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(neo4jPort.url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Neo4jSummary = await res.json();
      setSummary(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch Neo4j summary');
    } finally {
      setLoading(false);
    }
  }, [neo4jPort?.url]);

  useEffect(() => {
    if (neo4jPort?.url) fetchSummary();
  }, [neo4jPort?.url]);

  const elements = useMemo(() => (summary?.connected ? buildElements(summary) : []), [summary]);
  const stylesheet = useMemo(() => buildStylesheet(isDarkMode), [isDarkMode]);

  const wireEvents = useCallback((cy: Core) => {
    cy.removeAllListeners();
    cy.on('mouseover', 'node.kg-node', (e) => e.target.addClass('hover'));
    cy.on('mouseout', 'node.kg-node', (e) => e.target.removeClass('hover'));
    cy.on('mouseover', 'edge.kg-edge', (e) => e.target.addClass('hover'));
    cy.on('mouseout', 'edge.kg-edge', (e) => e.target.removeClass('hover'));
  }, []);

  const runLayout = useCallback((cy: Core, name: LayoutType) => {
    if (layoutRef.current) layoutRef.current.stop();
    const inst = cy.layout(getLayoutConfig(name));
    layoutRef.current = inst;
    inst.run();
  }, []);

  const applyLayout = useCallback((name: LayoutType) => {
    if (cyRef.current) runLayout(cyRef.current, name);
    if (fullCyRef.current) runLayout(fullCyRef.current, name);
  }, [runLayout]);

  const handleLayoutChange = (name: LayoutType) => {
    setLayout(name);
    applyLayout(name);
  };

  const makeHandlers = (ref: React.MutableRefObject<Core | null>) => ({
    zoomIn: () => ref.current && ref.current.zoom(ref.current.zoom() * 1.3),
    zoomOut: () => ref.current && ref.current.zoom(ref.current.zoom() / 1.3),
    fit: () => ref.current?.fit(undefined, 60),
    reset: () => ref.current && runLayout(ref.current, layout),
  });

  const mainHandlers = makeHandlers(cyRef);
  const fullHandlers = makeHandlers(fullCyRef);

  const nodeCount = elements.filter(e => (e.classes as string)?.includes('kg-node')).length;
  const edgeCount = elements.filter(e => (e.classes as string)?.includes('kg-edge')).length;

  const mainCyCallback = useCallback((cy: Core) => {
    cyRef.current = cy;
    wireEvents(cy);
    if (elements.length > 0) setTimeout(() => runLayout(cy, layout), 80);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wireEvents, runLayout]);

  const fullCyCallback = useCallback((cy: Core) => {
    fullCyRef.current = cy;
    wireEvents(cy);
    if (elements.length > 0) setTimeout(() => runLayout(cy, layout), 80);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wireEvents, runLayout]);

  if (!neo4jPort) return null;

  return (
    <>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Database className="h-4 w-4" />
              Knowledge Graph
            </span>
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={fetchSummary} disabled={loading}>
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            </Button>
          </CardTitle>
          {summary && (
            <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
              <span className="flex items-center gap-1.5 text-xs">
                <Circle className={`h-2 w-2 fill-current ${summary.connected ? 'text-green-500' : 'text-destructive'}`} />
                {summary.database}
              </span>
              <Badge variant="outline" className="text-xs h-5">{summary.graph.total_nodes.toLocaleString()} nodes</Badge>
              <Badge variant="outline" className="text-xs h-5">{summary.graph.total_relationships.toLocaleString()} rels</Badge>
              {Object.entries(summary.freshness)
                .filter(([k]) => k !== 'id')
                .map(([feed, date]) => (
                  <span key={feed} className="text-xs text-muted-foreground">
                    <span className="font-medium">{feed}</span>: {date}
                  </span>
                ))}
            </CardDescription>
          )}
        </CardHeader>

        <CardContent className="p-0">
          {loading && !summary && (
            <div className="flex items-center gap-2 text-muted-foreground text-sm p-4">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading graph…
            </div>
          )}

          {error && <div className="text-sm text-destructive p-4">{error}</div>}

          {summary && !summary.connected && (
            <div className="text-sm text-muted-foreground p-4">
              {summary.error ?? 'Cannot connect to Neo4j'}
            </div>
          )}

          {summary?.connected && elements.length > 0 && (
            <>
              <GraphControls
                layout={layout}
                onLayoutChange={handleLayoutChange}
                onZoomIn={mainHandlers.zoomIn}
                onZoomOut={mainHandlers.zoomOut}
                onFit={mainHandlers.fit}
                onReset={mainHandlers.reset}
                onFullscreen={() => setIsFullscreen(true)}
                nodeCount={nodeCount}
                edgeCount={edgeCount}
              />
              <div className="rounded-b-lg overflow-hidden bg-muted/10" style={{ height: 680 }}>
                <CytoscapeComponent
                  elements={elements}
                  stylesheet={stylesheet}
                  style={{ width: '100%', height: '100%' }}
                  cy={mainCyCallback}
                  wheelSensitivity={0.3}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Fullscreen dialog */}
      <Dialog open={isFullscreen} onOpenChange={setIsFullscreen}>
        <DialogContent className="max-w-[95vw] w-[95vw] h-[90vh] flex flex-col p-0 gap-0">
          <DialogHeader className="px-4 pt-4 pb-0 shrink-0">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Database className="h-4 w-4" />
              Knowledge Graph — {summary?.database}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col flex-1 min-h-0 mt-3">
            <GraphControls
              layout={layout}
              onLayoutChange={handleLayoutChange}
              onZoomIn={fullHandlers.zoomIn}
              onZoomOut={fullHandlers.zoomOut}
              onFit={fullHandlers.fit}
              onReset={fullHandlers.reset}
              nodeCount={nodeCount}
              edgeCount={edgeCount}
            />
            <div className="flex-1 min-h-0">
              <CytoscapeComponent
                elements={elements}
                stylesheet={stylesheet}
                style={{ width: '100%', height: '100%' }}
                cy={fullCyCallback}
                wheelSensitivity={0.3}
              />
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
