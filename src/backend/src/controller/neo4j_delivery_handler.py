"""Neo4j Delivery Handler — reads metadata from Neo4j graph databases.

This handler extends Ontos delivery capabilities to support Neo4j as a sink
for derived data products (Knowledge Graphs). It enables:
  - Querying Neo4j for graph metadata (node labels, relationships, counts)
  - Validating connectivity to Neo4j instances
  - Reporting data freshness from Incremental tracker nodes

Architecture context:
  - The feeder engine (neo4j-feeder-engine) handles the ETL: Databricks -> Neo4j
  - This handler handles the catalog/governance: Ontos -> Neo4j metadata
  - They are complementary, not competing

Security:
  - Connection details are resolved server-side from data product configuration
  - Callers never supply bolt_url or secret identifiers directly
  - All queries are read-only (no graph mutations)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase, READ_ACCESS
from neo4j.exceptions import ServiceUnavailable, AuthError

logger = logging.getLogger(__name__)

# Simple TTL cache for metadata results (60 seconds default)
_CACHE_TTL_SECONDS = 60
_cache: Dict[str, Dict[str, Any]] = {}


def _cache_key(bolt_url: str, database: str) -> str:
    return f"{bolt_url}|{database}"


def _get_cached(key: str) -> Optional[Dict[str, Any]]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL_SECONDS:
        return entry["data"]
    return None


def _set_cached(key: str, data: Any) -> None:
    _cache[key] = {"ts": time.time(), "data": data}


# Query timeout in seconds — prevents runaway scans on large graphs
_QUERY_TIMEOUT_SECONDS = 10


@dataclass
class TopologyEdge:
    """One (from_label)-[rel_type]->(to_label) edge in the graph schema topology."""
    from_label: str
    rel_type: str
    to_label: str
    count: int


@dataclass
class Neo4jGraphMetadata:
    """Metadata extracted from a Neo4j graph database."""
    node_labels: List[str]
    relationship_types: List[str]
    node_counts: Dict[str, int]
    relationship_counts: Dict[str, int]
    total_nodes: int
    total_relationships: int
    topology: List[TopologyEdge]
    database: str
    connected: bool
    error: Optional[str] = None


class Neo4jDeliveryHandler:
    """Handles read-only metadata queries for Neo4j sink output ports.

    Responsibilities:
      - Validate connectivity to Neo4j instances
      - Extract graph metadata (labels, relationships, counts)
      - Report freshness via Incremental tracker nodes
    """

    def __init__(self, bolt_url: str, username: str, password: str, database: str = "neo4j"):
        self._bolt_url = bolt_url
        self._username = username
        self._password = password
        self._database = database
        self._driver = None

    @property
    def driver(self):
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                self._bolt_url,
                auth=(self._username, self._password),
                connection_timeout=10,
                max_transaction_retry_time=5,
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    # -------------------------------------------------------------------------
    # Connectivity & metadata
    # -------------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Validate connectivity to the Neo4j instance."""
        try:
            with self.driver.session(
                database=self._database,
                default_access_mode=READ_ACCESS,
            ) as session:
                result = session.run("RETURN 1 AS connected")
                result.single()
            return {"connected": True, "database": self._database}
        except ServiceUnavailable as e:
            return {"connected": False, "error": f"Service unavailable: {e}"}
        except AuthError as e:
            return {"connected": False, "error": f"Authentication failed: {e}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def get_graph_metadata(self) -> Neo4jGraphMetadata:
        """Extract full graph metadata — node labels, relationships, counts.

        Results are cached for 60 seconds to avoid repeated full scans.
        Queries use a 10-second timeout to prevent runaway operations.
        """
        cache_key = _cache_key(self._bolt_url, self._database)
        cached = _get_cached(cache_key)
        if cached:
            return cached

        try:
            with self.driver.session(
                database=self._database,
                default_access_mode=READ_ACCESS,
            ) as session:
                # Node labels and counts (with timeout)
                node_result = session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count "
                    "ORDER BY count DESC",
                    timeout=_QUERY_TIMEOUT_SECONDS,
                )
                node_counts = {r["label"]: r["count"] for r in node_result}

                # Relationship types and counts
                rel_result = session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
                    "ORDER BY count DESC",
                    timeout=_QUERY_TIMEOUT_SECONDS,
                )
                relationship_counts = {r["type"]: r["count"] for r in rel_result}

                # Topology: (from_label)-[rel_type]->(to_label)
                topo_result = session.run(
                    "MATCH (a)-[r]->(b) "
                    "RETURN labels(a)[0] AS from_label, type(r) AS rel_type, "
                    "labels(b)[0] AS to_label, count(*) AS count "
                    "ORDER BY from_label, rel_type",
                    timeout=_QUERY_TIMEOUT_SECONDS,
                )
                topology = [
                    TopologyEdge(
                        from_label=row["from_label"],
                        rel_type=row["rel_type"],
                        to_label=row["to_label"],
                        count=row["count"],
                    )
                    for row in topo_result
                ]

                metadata = Neo4jGraphMetadata(
                    node_labels=list(node_counts.keys()),
                    relationship_types=list(relationship_counts.keys()),
                    node_counts=node_counts,
                    relationship_counts=relationship_counts,
                    total_nodes=sum(node_counts.values()),
                    total_relationships=sum(relationship_counts.values()),
                    topology=topology,
                    database=self._database,
                    connected=True,
                )

                _set_cached(cache_key, metadata)
                return metadata

        except Exception as e:
            logger.error(f"Failed to get graph metadata: {e}", exc_info=True)
            return Neo4jGraphMetadata(
                node_labels=[],
                relationship_types=[],
                node_counts={},
                relationship_counts={},
                total_nodes=0,
                total_relationships=0,
                topology=[],
                database=self._database,
                connected=False,
                error=str(e),
            )

    def get_freshness(self) -> Dict[str, Optional[str]]:
        """Read the Incremental tracker node to report data freshness per feed.

        The feeder engine writes an Incremental node like:
          (:Incremental {schema: "V3", flightlegs: "2026-05-27", alerts: "2026-05-27", ...})

        Returns a dict of feed_name -> last_load_date.
        """
        try:
            with self.driver.session(
                database=self._database,
                default_access_mode=READ_ACCESS,
            ) as session:
                result = session.run(
                    "MATCH (n:Incremental) RETURN properties(n) AS props LIMIT 1",
                    timeout=_QUERY_TIMEOUT_SECONDS,
                )
                record = result.single()
                if record:
                    props = dict(record["props"])
                    props.pop("schema", None)
                    return props
                return {}
        except Exception as e:
            logger.warning(f"Could not read Incremental tracker: {e}")
            return {}

    def get_product_summary(self) -> Dict[str, Any]:
        """Get a complete summary suitable for display in Ontos product detail view."""
        metadata = self.get_graph_metadata()
        freshness = self.get_freshness() if metadata.connected else {}

        return {
            "connected": metadata.connected,
            "error": metadata.error,
            "database": metadata.database,
            "graph": {
                "node_labels": metadata.node_labels,
                "relationship_types": metadata.relationship_types,
                "node_counts": metadata.node_counts,
                "relationship_counts": metadata.relationship_counts,
                "total_nodes": metadata.total_nodes,
                "total_relationships": metadata.total_relationships,
                "topology": [
                    {
                        "from_label": e.from_label,
                        "rel_type": e.rel_type,
                        "to_label": e.to_label,
                        "count": e.count,
                    }
                    for e in metadata.topology
                ],
            },
            "freshness": freshness,
        }
