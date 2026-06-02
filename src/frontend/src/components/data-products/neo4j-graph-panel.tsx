/**
 * Neo4j Graph Panel — displays graph metadata for derived data products.
 *
 * Shows: node labels + counts, relationship types + counts, data freshness per feed,
 * connectivity status. Used in the data product detail view when the output port
 * is a Neo4j Knowledge Graph.
 */

import { useEffect, useState } from "react";
import { useApi } from "../../hooks/use-api";

interface Neo4jSummary {
  connected: boolean;
  error?: string;
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
  boltUrl: string;
  username?: string;
  database?: string;
}

export function Neo4jGraphPanel({
  boltUrl,
  username = "neo4j",
  database = "neo4j",
}: Neo4jGraphPanelProps) {
  const api = useApi();
  const [summary, setSummary] = useState<Neo4jSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSummary() {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          bolt_url: boltUrl,
          username,
          database,
        });
        const response = await api.get(`/api/neo4j/summary?${params}`);
        setSummary(response.data);
      } catch (err: any) {
        setError(err.message || "Failed to connect to Neo4j");
      } finally {
        setLoading(false);
      }
    }
    if (boltUrl) {
      fetchSummary();
    }
  }, [boltUrl, username, database]);

  if (loading) {
    return (
      <div className="p-4 border rounded-lg bg-muted/50">
        <p className="text-sm text-muted-foreground">Connecting to Neo4j...</p>
      </div>
    );
  }

  if (error || !summary) {
    return (
      <div className="p-4 border rounded-lg border-destructive/50 bg-destructive/5">
        <h4 className="text-sm font-medium text-destructive">Neo4j Connection Failed</h4>
        <p className="text-xs text-muted-foreground mt-1">{error || "Unknown error"}</p>
        <p className="text-xs text-muted-foreground mt-1">Bolt URL: {boltUrl}</p>
      </div>
    );
  }

  if (!summary.connected) {
    return (
      <div className="p-4 border rounded-lg border-yellow-500/50 bg-yellow-500/5">
        <h4 className="text-sm font-medium text-yellow-700">Neo4j Unreachable</h4>
        <p className="text-xs text-muted-foreground mt-1">{summary.error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-green-500" />
          <h4 className="text-sm font-medium">Knowledge Graph — {summary.database}</h4>
        </div>
        <span className="text-xs text-muted-foreground">
          {summary.graph.total_nodes.toLocaleString()} nodes · {summary.graph.total_relationships.toLocaleString()} relationships
        </span>
      </div>

      {/* Node Labels */}
      <div className="border rounded-lg p-3">
        <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Node Labels ({summary.graph.node_labels.length})
        </h5>
        <div className="flex flex-wrap gap-1.5">
          {summary.graph.node_labels.map((label) => (
            <span
              key={label}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
            >
              {label}
              <span className="text-blue-600/70 dark:text-blue-400/70">
                {summary.graph.node_counts[label]?.toLocaleString()}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Relationship Types */}
      <div className="border rounded-lg p-3">
        <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
          Relationships ({summary.graph.relationship_types.length})
        </h5>
        <div className="flex flex-wrap gap-1.5">
          {summary.graph.relationship_types.map((type) => (
            <span
              key={type}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300"
            >
              {type}
              <span className="text-purple-600/70 dark:text-purple-400/70">
                {summary.graph.relationship_counts[type]?.toLocaleString()}
              </span>
            </span>
          ))}
        </div>
      </div>

      {/* Data Freshness */}
      {Object.keys(summary.freshness).length > 0 && (
        <div className="border rounded-lg p-3">
          <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-2">
            Data Freshness (Last Load)
          </h5>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {Object.entries(summary.freshness).map(([feed, date]) => (
              <div key={feed} className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">{feed}</span>
                <span className="font-mono">{date}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Connection Info */}
      <div className="text-xs text-muted-foreground border-t pt-2">
        <span className="font-mono">{summary.bolt_url}</span>
      </div>
    </div>
  );
}
