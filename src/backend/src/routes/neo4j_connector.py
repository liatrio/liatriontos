"""Neo4j Connector API routes — exposes graph metadata for derived data products.

Endpoints:
  GET  /api/neo4j/health         — Check connectivity to a Neo4j instance
  GET  /api/neo4j/metadata       — Get graph metadata (labels, relationships, counts)
  GET  /api/neo4j/freshness      — Get data freshness per feed (from Incremental tracker)
  GET  /api/neo4j/summary        — Get full product summary (metadata + freshness)
"""

from fastapi import APIRouter, HTTPException, Query

from ..common.logging import get_logger
from ..controller.neo4j_delivery_handler import Neo4jDeliveryHandler

logger = get_logger(__name__)

router = APIRouter(prefix="/api/neo4j", tags=["Neo4j Connector"])


def _get_handler(
    bolt_url: str,
    username: str = "neo4j",
    database: str = "neo4j",
) -> Neo4jDeliveryHandler:
    """Create a handler from query params.

    In production, credentials should be resolved from the connections table
    or Databricks UC Secrets — never passed as query parameters.
    """
    # TODO: Resolve password from connections table or UC Secrets
    # For now, use env var as fallback
    import os
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return Neo4jDeliveryHandler(
        bolt_url=bolt_url,
        username=username,
        password=password,
        database=database,
    )


@router.get("/health")
def neo4j_health(
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
):
    """Check connectivity to a Neo4j instance."""
    handler = _get_handler(bolt_url, username, database)
    try:
        return handler.health_check()
    finally:
        handler.close()


@router.get("/metadata")
def neo4j_metadata(
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
):
    """Get graph metadata — node labels, relationship types, counts."""
    handler = _get_handler(bolt_url, username, database)
    try:
        metadata = handler.get_graph_metadata()
        if not metadata.connected:
            raise HTTPException(status_code=503, detail=metadata.error)
        return {
            "node_labels": metadata.node_labels,
            "relationship_types": metadata.relationship_types,
            "node_counts": metadata.node_counts,
            "relationship_counts": metadata.relationship_counts,
            "total_nodes": metadata.total_nodes,
            "total_relationships": metadata.total_relationships,
            "database": metadata.database,
        }
    finally:
        handler.close()


@router.get("/freshness")
def neo4j_freshness(
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
):
    """Get data freshness per feed from the Incremental tracker node."""
    handler = _get_handler(bolt_url, username, database)
    try:
        return handler.get_freshness()
    finally:
        handler.close()


@router.get("/summary")
def neo4j_summary(
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
):
    """Get full product summary — metadata + freshness + connectivity status."""
    handler = _get_handler(bolt_url, username, database)
    try:
        return handler.get_product_summary()
    finally:
        handler.close()
