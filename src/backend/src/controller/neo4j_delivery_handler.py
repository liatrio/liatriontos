"""Neo4j Delivery Handler — writes/provisions access to Neo4j graph databases.

This handler extends Ontos delivery capabilities to support Neo4j as a sink
for derived data products (Knowledge Graphs). It enables:
  - Querying Neo4j for graph metadata (node labels, relationships, counts)
  - Validating connectivity to Neo4j instances
  - Future: provisioning read access to Neo4j databases

Architecture context:
  - The feeder engine (neo4j-feeder-engine) handles the ETL: Databricks → Neo4j
  - This handler handles the catalog/governance: Ontos → Neo4j metadata
  - They are complementary, not competing
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

logger = logging.getLogger(__name__)


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
    """Handles delivery operations for Neo4j sink output ports.

    Responsibilities:
      - Validate connectivity to Neo4j instances
      - Extract graph metadata (labels, relationships, counts)
      - Report freshness via Incremental tracker nodes
      - Future: manage read-access provisioning to Neo4j
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
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def health_check(self) -> Dict[str, Any]:
        """Validate connectivity to the Neo4j instance."""
        try:
            with self.driver.session(database=self._database) as session:
                result = session.run("RETURN 1 AS connected")
                result.single()
            return {"connected": True, "bolt_url": self._bolt_url, "database": self._database}
        except ServiceUnavailable as e:
            return {"connected": False, "error": f"Service unavailable: {e}"}
        except AuthError as e:
            return {"connected": False, "error": f"Authentication failed: {e}"}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    def get_graph_metadata(self) -> Neo4jGraphMetadata:
        """Extract full graph metadata — node labels, relationships, counts."""
        try:
            with self.driver.session(database=self._database) as session:
                # Node labels and counts
                node_result = session.run(
                    "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count "
                    "ORDER BY count DESC"
                )
                node_counts = {r["label"]: r["count"] for r in node_result}

                # Relationship types and counts
                rel_result = session.run(
                    "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
                    "ORDER BY count DESC"
                )
                relationship_counts = {r["type"]: r["count"] for r in rel_result}

                # Topology: (from_label)-[rel_type]->(to_label)
                topo_result = session.run(
                    "MATCH (a)-[r]->(b) "
                    "RETURN labels(a)[0] AS from_label, type(r) AS rel_type, "
                    "labels(b)[0] AS to_label, count(*) AS count "
                    "ORDER BY from_label, rel_type"
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

                return Neo4jGraphMetadata(
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

        Returns a dict of feed_name → last_load_date.
        """
        try:
            with self.driver.session(database=self._database) as session:
                result = session.run(
                    "MATCH (n:Incremental) RETURN properties(n) AS props LIMIT 1"
                )
                record = result.single()
                if record:
                    props = dict(record["props"])
                    # Remove the schema key, return only feed dates
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
            "bolt_url": self._bolt_url,
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
