import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Loader2, RefreshCw, Database, CircleDot } from 'lucide-react';
import type { ManagementPort } from '@/types/data-product';

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
  };
  freshness: Record<string, string>;
}

interface Neo4jGraphPanelProps {
  managementPorts?: ManagementPort[];
}

export default function Neo4jGraphPanel({ managementPorts }: Neo4jGraphPanelProps) {
  const [summary, setSummary] = useState<Neo4jSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Find a neo4j management port (observability type with neo4j in URL)
  const neo4jPort = managementPorts?.find(
    (p) => p.url && (p.url.includes('neo4j') || p.name?.toLowerCase().includes('neo4j'))
  );

  const fetchSummary = async () => {
    if (!neo4jPort?.url) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(neo4jPort.url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setSummary(data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch Neo4j summary');
    } finally {
      setLoading(false);
    }
  };

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
      <CardContent>
        {loading && !summary && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading graph metadata...
          </div>
        )}

        {error && (
          <div className="text-sm text-destructive">{error}</div>
        )}

        {summary && (
          <div className="space-y-2">
            <pre className="bg-muted/50 rounded-lg p-4 text-xs font-mono overflow-x-auto whitespace-pre">
{`# Neo4j Knowledge Graph — Live State
# Source: ${neo4jPort.url?.split('?')[0]}
---
connection:
  bolt_url: "${summary.bolt_url}"
  database: ${summary.database}
  status: ${summary.connected ? 'connected' : 'disconnected'}

graph:
  total_nodes: ${summary.graph.total_nodes}
  total_relationships: ${summary.graph.total_relationships}

  node_labels:
${summary.graph.node_labels.map(l => `    - ${l}: ${summary.graph.node_counts[l]}`).join('\n')}

  relationships:
${summary.graph.relationship_types.map(r => `    - ${r}: ${summary.graph.relationship_counts[r]}`).join('\n')}

freshness:
${Object.entries(summary.freshness).map(([feed, date]) => `  ${feed}: "${date}"`).join('\n')}`}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
