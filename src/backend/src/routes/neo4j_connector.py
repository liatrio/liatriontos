"""Neo4j Connector API routes — exposes graph metadata for derived data products.

Endpoints:
  GET  /api/neo4j/health         — Check connectivity to a Neo4j instance
  GET  /api/neo4j/metadata       — Get graph metadata (labels, relationships, counts)
  GET  /api/neo4j/freshness      — Get data freshness per feed (from Incremental tracker)
  GET  /api/neo4j/summary        — Get full product summary (metadata + freshness)

Authentication:
  Pass secret_scope + secret_key to resolve the Neo4j password from a Databricks
  UC Secret Scope at request time. Falls back to NEO4J_PASSWORD env var for local dev.
"""

import base64
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from databricks.sdk import WorkspaceClient

from ..common.dependencies import WorkspaceClientDep
from ..common.logging import get_logger
from ..controller.neo4j_delivery_handler import Neo4jDeliveryHandler

logger = get_logger(__name__)

router = APIRouter(prefix="/api/neo4j", tags=["Neo4j Connector"])


def _resolve_password(
    ws: WorkspaceClient,
    secret_scope: Optional[str],
    secret_key: Optional[str],
) -> str:
    """Resolve the Neo4j password from a UC Secret Scope, falling back to env var."""
    if secret_scope and secret_key:
        try:
            resp = ws.secrets.get_secret(scope=secret_scope, key=secret_key)
            raw = resp.value
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            text = text.strip()
            # The REST API base64-encodes values; decode if not already plain text
            try:
                text = base64.b64decode(text).decode("utf-8").strip()
            except Exception:
                pass
            return text
        except Exception as e:
            logger.error(f"Failed to resolve Neo4j password from secret '{secret_scope}/{secret_key}': {e}")
            raise HTTPException(status_code=500, detail=f"Could not resolve Neo4j credentials from secret scope: {e}")
    return os.environ.get("NEO4J_PASSWORD", "password")


def _get_handler(
    bolt_url: str,
    ws: WorkspaceClient,
    username: str = "neo4j",
    database: str = "neo4j",
    secret_scope: Optional[str] = None,
    secret_key: Optional[str] = None,
) -> Neo4jDeliveryHandler:
    password = _resolve_password(ws, secret_scope, secret_key)
    return Neo4jDeliveryHandler(
        bolt_url=bolt_url,
        username=username,
        password=password,
        database=database,
    )


@router.get("/health")
def neo4j_health(
    ws: WorkspaceClientDep,
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
    secret_scope: Optional[str] = Query(None, description="Databricks UC Secret scope containing the Neo4j password"),
    secret_key: Optional[str] = Query(None, description="Key within the secret scope"),
):
    """Check connectivity to a Neo4j instance."""
    handler = _get_handler(bolt_url, ws, username, database, secret_scope, secret_key)
    try:
        return handler.health_check()
    finally:
        handler.close()


@router.get("/metadata")
def neo4j_metadata(
    ws: WorkspaceClientDep,
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
    secret_scope: Optional[str] = Query(None, description="Databricks UC Secret scope containing the Neo4j password"),
    secret_key: Optional[str] = Query(None, description="Key within the secret scope"),
):
    """Get graph metadata — node labels, relationship types, counts."""
    handler = _get_handler(bolt_url, ws, username, database, secret_scope, secret_key)
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
    ws: WorkspaceClientDep,
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
    secret_scope: Optional[str] = Query(None, description="Databricks UC Secret scope containing the Neo4j password"),
    secret_key: Optional[str] = Query(None, description="Key within the secret scope"),
):
    """Get data freshness per feed from the Incremental tracker node."""
    handler = _get_handler(bolt_url, ws, username, database, secret_scope, secret_key)
    try:
        return handler.get_freshness()
    finally:
        handler.close()


@router.get("/summary")
def neo4j_summary(
    ws: WorkspaceClientDep,
    bolt_url: str = Query(..., description="Neo4j Bolt URL"),
    username: str = Query("neo4j", description="Neo4j username"),
    database: str = Query("neo4j", description="Neo4j database"),
    secret_scope: Optional[str] = Query(None, description="Databricks UC Secret scope containing the Neo4j password"),
    secret_key: Optional[str] = Query(None, description="Key within the secret scope"),
):
    """Get full product summary — metadata + freshness + connectivity status."""
    handler = _get_handler(bolt_url, ws, username, database, secret_scope, secret_key)
    try:
        return handler.get_product_summary()
    finally:
        handler.close()
