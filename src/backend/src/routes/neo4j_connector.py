"""Neo4j Connector API routes — exposes graph metadata for registered data products.

Endpoints:
  GET  /api/neo4j/{product_id}/health     — Check connectivity to the product's Neo4j instance
  GET  /api/neo4j/{product_id}/metadata   — Get graph metadata (labels, relationships, counts)
  GET  /api/neo4j/{product_id}/freshness  — Get data freshness per feed (from Incremental tracker)
  GET  /api/neo4j/{product_id}/summary    — Get full product summary (metadata + freshness)

Security:
  All endpoints require READ_ONLY permission on 'data-products'.
  Neo4j connection details are resolved server-side from the data product's
  output port configuration — callers never supply credentials or host URLs.
"""

import json
import os
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from databricks.sdk import WorkspaceClient

from ..common.authorization import PermissionChecker
from ..common.dependencies import WorkspaceClientDep, DataProductsManagerDep
from ..common.features import FeatureAccessLevel
from ..common.logging import get_logger
from ..controller.neo4j_delivery_handler import Neo4jDeliveryHandler

logger = get_logger(__name__)

router = APIRouter(prefix="/api/neo4j", tags=["Neo4j Connector"])

DATA_PRODUCTS_FEATURE_ID = "data-products"


def _get_allowed_hosts() -> set:
    """Return the set of allowed Neo4j hosts from environment config.

    Set NEO4J_ALLOWED_HOSTS as a comma-separated list of hostnames/IPs.
    If not set, all hosts are rejected (fail-closed).
    Example: NEO4J_ALLOWED_HOSTS=oem-kg.neo4j.internal,localhost
    """
    raw = os.environ.get("NEO4J_ALLOWED_HOSTS", "")
    if not raw.strip():
        return set()
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _validate_bolt_host(bolt_url: str) -> None:
    """Validate that the bolt URL points to an allowed host.

    Prevents SSRF via persisted product config — even if a user edits the
    output port's server.host, the backend will only connect to allowlisted hosts.
    """
    allowed = _get_allowed_hosts()
    if not allowed:
        # No allowlist configured — reject all connections in production,
        # allow all in local dev (when NEO4J_ALLOWED_HOSTS is unset and
        # ENV=LOCAL)
        env = os.environ.get("ENV", "").upper()
        if env == "LOCAL":
            return
        raise HTTPException(
            status_code=403,
            detail="NEO4J_ALLOWED_HOSTS is not configured. Cannot connect to Neo4j.",
        )

    # Extract hostname from bolt URL (bolt://host:port or neo4j://host:port)
    from urllib.parse import urlparse
    parsed = urlparse(bolt_url)
    host = (parsed.hostname or "").lower()

    if host not in allowed:
        logger.warning(f"Neo4j host '{host}' not in allowed hosts: {allowed}")
        raise HTTPException(
            status_code=403,
            detail=f"Neo4j host '{host}' is not in the allowed hosts list.",
        )


def _resolve_neo4j_config(product, ws: WorkspaceClient) -> dict:
    """Extract Neo4j connection config from a data product's output ports.

    Looks for an output port with port_type containing 'neo4j' or a server
    block with a bolt_url/host field. Returns a dict with bolt_url, username,
    database, and password.

    Raises HTTPException if no Neo4j output port is found.
    """
    neo4j_port = None

    for port in (product.outputPorts or []):
        # Check port_type first
        if port.type and "neo4j" in port.type.lower():
            neo4j_port = port
            break
        # Fall back to checking server for bolt-like host
        if port.server:
            host = getattr(port.server, "host", None) or ""
            if "bolt" in host.lower() or "neo4j" in host.lower():
                neo4j_port = port
                break

    if not neo4j_port:
        raise HTTPException(
            status_code=404,
            detail="No Neo4j output port found on this data product."
        )

    # Extract connection details from the Server model
    server = neo4j_port.server
    if not server:
        raise HTTPException(
            status_code=422,
            detail="Neo4j output port has no server configuration."
        )

    # The bolt URL is stored in the 'host' field of the Server model
    bolt_url = getattr(server, "host", None) or ""
    if not bolt_url:
        raise HTTPException(
            status_code=422,
            detail="Neo4j output port has no host (bolt_url) configured in its server field."
        )

    # Validate against allowed hosts (prevents SSRF via persisted config)
    _validate_bolt_host(bolt_url)

    database = getattr(server, "database", None) or "neo4j"

    # Username comes from additionalProperties or defaults to "neo4j"
    username = "neo4j"
    additional = getattr(server, "additionalProperties", None)
    if additional:
        try:
            extra = json.loads(additional) if isinstance(additional, str) else additional
            if isinstance(extra, dict):
                username = extra.get("username", username)
        except (json.JSONDecodeError, TypeError):
            pass

    # Resolve password from custom properties (secret_scope/secret_key) or env var
    password = None
    secret_scope = None
    secret_key = None

    # Check output port custom properties for secret references
    for cp in (neo4j_port.customProperties or []):
        prop_name = getattr(cp, "property", "") or getattr(cp, "name", "")
        prop_value = getattr(cp, "value", "")
        if prop_name == "secret_scope":
            secret_scope = prop_value
        elif prop_name == "secret_key":
            secret_key = prop_value

    if secret_scope and secret_key:
        try:
            import base64
            resp = ws.secrets.get_secret(scope=secret_scope, key=secret_key)
            raw = resp.value
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            text = text.strip()
            try:
                text = base64.b64decode(text).decode("utf-8").strip()
            except Exception:
                pass
            password = text
        except Exception as e:
            logger.error(f"Failed to resolve Neo4j password from secret '{secret_scope}/{secret_key}': {e}")
            raise HTTPException(
                status_code=500,
                detail="Could not resolve Neo4j credentials from configured secret scope."
            )
    else:
        password = os.environ.get("NEO4J_PASSWORD")
        if not password:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Neo4j credentials are not configured. "
                    "Set output port secret_scope/secret_key or NEO4J_PASSWORD."
                ),
            )

    return {
        "bolt_url": bolt_url,
        "username": username,
        "password": password,
        "database": database,
    }


def _get_handler_for_product(product, ws: WorkspaceClient) -> Neo4jDeliveryHandler:
    """Create a Neo4jDeliveryHandler from a data product's configuration."""
    config = _resolve_neo4j_config(product, ws)
    return Neo4jDeliveryHandler(
        bolt_url=config["bolt_url"],
        username=config["username"],
        password=config["password"],
        database=config["database"],
    )


@router.get("/{product_id}/health")
def neo4j_health(
    product_id: str,
    ws: WorkspaceClientDep,
    manager: DataProductsManagerDep,
    _: bool = Depends(PermissionChecker(DATA_PRODUCTS_FEATURE_ID, FeatureAccessLevel.READ_ONLY)),
):
    """Check connectivity to the Neo4j instance configured on a data product."""
    product = manager.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found.")

    handler = _get_handler_for_product(product, ws)
    try:
        return handler.health_check()
    finally:
        handler.close()


@router.get("/{product_id}/metadata")
def neo4j_metadata(
    product_id: str,
    ws: WorkspaceClientDep,
    manager: DataProductsManagerDep,
    _: bool = Depends(PermissionChecker(DATA_PRODUCTS_FEATURE_ID, FeatureAccessLevel.READ_ONLY)),
):
    """Get graph metadata — node labels, relationship types, counts."""
    product = manager.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found.")

    handler = _get_handler_for_product(product, ws)
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


@router.get("/{product_id}/freshness")
def neo4j_freshness(
    product_id: str,
    ws: WorkspaceClientDep,
    manager: DataProductsManagerDep,
    _: bool = Depends(PermissionChecker(DATA_PRODUCTS_FEATURE_ID, FeatureAccessLevel.READ_ONLY)),
):
    """Get data freshness per feed from the Incremental tracker node."""
    product = manager.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found.")

    handler = _get_handler_for_product(product, ws)
    try:
        return handler.get_freshness()
    finally:
        handler.close()


@router.get("/{product_id}/summary")
def neo4j_summary(
    product_id: str,
    ws: WorkspaceClientDep,
    manager: DataProductsManagerDep,
    _: bool = Depends(PermissionChecker(DATA_PRODUCTS_FEATURE_ID, FeatureAccessLevel.READ_ONLY)),
):
    """Get full product summary — metadata + freshness + connectivity status."""
    product = manager.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Data product not found.")

    handler = _get_handler_for_product(product, ws)
    try:
        return handler.get_product_summary()
    finally:
        handler.close()
