"""Neo4j connector — end-to-end tests for the graph integration feature.

Tests cover:
  1. Neo4j API endpoints (health, metadata, freshness, summary)
  2. Data product readiness checks with contract + graph attribute sync
  3. Idempotency of sync-graph-attributes
  4. Product change-analyzer null-safety fix (team field)

Runs against the local dev server (localhost:8000) with MOCK_USER_DETAILS=True.
Skips automatically if the server or Neo4j is unreachable.
"""

import pytest
import requests

BASE_URL = "http://localhost:8000"
BOLT_URL = "bolt://localhost:7687"
NEO4J_DB = "neo4j"
PRODUCT_ID = "e36589cd-3559-41d1-95d0-cbe713519dfd"  # Flight Ops KG product


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api():
    """Unauthenticated requests.Session for the local dev server (mock auth)."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})
    try:
        resp = session.get(f"{BASE_URL}/api/health", timeout=5)
        resp.raise_for_status()
    except Exception as exc:
        pytest.skip(f"Backend not reachable at {BASE_URL}: {exc}")
    yield session
    session.close()


@pytest.fixture(scope="module")
def neo4j_available(api):
    """Skip the test if Neo4j is not reachable via the backend proxy."""
    resp = api.get(f"{BASE_URL}/api/neo4j/health", params={"bolt_url": BOLT_URL, "database": NEO4J_DB})
    data = resp.json()
    if not data.get("connected"):
        pytest.skip(f"Neo4j not reachable: {data.get('error', 'unknown')}")


# ---------------------------------------------------------------------------
# 1. Backend health
# ---------------------------------------------------------------------------

class TestBackendHealth:

    @pytest.mark.smoke
    def test_health_db_and_ws(self, api):
        resp = api.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["db_ok"] is True, f"DB not OK: {body}"
        assert body["ws_ok"] is True, f"Workspace client not OK: {body}"
        assert body["warnings"] == []


# ---------------------------------------------------------------------------
# 2. Neo4j API endpoints
# ---------------------------------------------------------------------------

class TestNeo4jEndpoints:

    @pytest.mark.smoke
    def test_health_endpoint_returns_connected(self, api, neo4j_available):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/health",
            params={"bolt_url": BOLT_URL, "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        # error key is omitted when connected — treat missing as None
        assert body.get("error") is None

    @pytest.mark.readonly
    def test_metadata_returns_expected_labels(self, api, neo4j_available):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/metadata",
            params={"bolt_url": BOLT_URL, "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        labels = set(body["node_labels"])
        assert {"Aircraft", "FlightLeg", "Alert", "MaintenanceEvent", "Incremental"} <= labels
        assert body["total_nodes"] >= 8
        assert body["total_relationships"] >= 6

    @pytest.mark.readonly
    def test_metadata_returns_expected_relationships(self, api, neo4j_available):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/metadata",
            params={"bolt_url": BOLT_URL, "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        rel_types = set(body["relationship_types"])
        assert {"OPERATED", "TRIGGERED", "RESOLVED_BY", "TRACKED_BY"} <= rel_types

    @pytest.mark.readonly
    def test_freshness_returns_feeds(self, api, neo4j_available):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/freshness",
            params={"bolt_url": BOLT_URL, "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "shopfinding" in body
        assert "flightleg" in body
        assert "aircraft" in body

    @pytest.mark.readonly
    def test_summary_combines_metadata_and_freshness(self, api, neo4j_available):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/summary",
            params={"bolt_url": BOLT_URL, "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["bolt_url"] == BOLT_URL
        assert body["database"] == NEO4J_DB
        assert body["graph"]["total_nodes"] >= 8
        assert len(body["graph"]["node_labels"]) >= 5
        assert len(body["freshness"]) >= 3

    @pytest.mark.readonly
    def test_health_bad_url_returns_disconnected(self, api):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/health",
            params={"bolt_url": "bolt://nonexistent-host:9999", "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["error"] is not None

    @pytest.mark.readonly
    def test_summary_bad_url_returns_disconnected_not_500(self, api):
        resp = api.get(
            f"{BASE_URL}/api/neo4j/summary",
            params={"bolt_url": "bolt://nonexistent-host:9999", "database": NEO4J_DB},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False


# ---------------------------------------------------------------------------
# 3. Data product: contract linking and readiness
# ---------------------------------------------------------------------------

class TestDataProductReadiness:

    @pytest.mark.readonly
    def test_product_exists(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Flight Operations Knowledge Graph"
        assert body["status"] == "active"

    @pytest.mark.readonly
    def test_output_port_has_contract(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        # API returns camelCase keys
        ports = body.get("outputPorts") or body.get("output_ports") or []
        assert len(ports) >= 1, "Must have at least one output port"
        port = ports[0]
        contract_id = port.get("contractId") or port.get("contract_id")
        contract_name = port.get("contractName") or port.get("contract_name")
        assert contract_id, "Output port must have a contract_id linked"
        assert contract_name, "contract_name should be resolved"

    @pytest.mark.readonly
    def test_management_port_has_neo4j_url(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        mgmt_ports = body.get("managementPorts") or body.get("management_ports") or []
        neo4j_port = next((p for p in mgmt_ports if "neo4j" in (p.get("url") or "")), None)
        assert neo4j_port is not None, "Must have a management port with neo4j in the URL"
        assert neo4j_port["url"].startswith("http://localhost:8000/api/neo4j/summary")

    @pytest.mark.readonly
    def test_readiness_odps_metadata_passes(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/readiness")
        assert resp.status_code == 200
        checks = {c["name"]: c for c in resp.json()["checks"]}
        assert checks["ODPS metadata present"]["status"] == "pass"

    @pytest.mark.readonly
    def test_readiness_contract_passes(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/readiness")
        assert resp.status_code == 200
        checks = {c["name"]: c for c in resp.json()["checks"]}
        c = checks["At least one output contract"]
        assert c["status"] == "pass", c["detail"]
        assert "1 contract(s)" in c["detail"]

    @pytest.mark.readonly
    def test_readiness_logical_attributes_passes(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/readiness")
        assert resp.status_code == 200
        checks = {c["name"]: c for c in resp.json()["checks"]}
        c = checks["Key fields mapped to logical attributes"]
        assert c["status"] == "pass", c["detail"]
        attrs = int(c["detail"].split()[0])
        assert attrs >= 20, f"Expected ≥20 attributes, got: {c['detail']}"

    @pytest.mark.readonly
    def test_readiness_business_lineage_passes(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/readiness")
        assert resp.status_code == 200
        checks = {c["name"]: c for c in resp.json()["checks"]}
        assert checks["Business lineage defined (upstream)"]["status"] == "pass"

    @pytest.mark.readonly
    def test_readiness_overall_not_fail(self, api):
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/readiness")
        assert resp.status_code == 200
        overall = resp.json()["overall"]
        assert overall in ("ready", "partial"), f"Overall readiness is 'not_ready': {overall}"


# ---------------------------------------------------------------------------
# 4. sync-graph-attributes
# ---------------------------------------------------------------------------

class TestSyncGraphAttributes:

    @pytest.mark.crud
    def test_sync_returns_expected_counts(self, api):
        resp = api.post(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/sync-graph-attributes")
        assert resp.status_code == 200
        body = resp.json()
        # On re-run: all datasets reused, all attributes skipped
        total_datasets = body["datasets_created"] + body["datasets_reused"]
        total_attrs = body["attributes_linked"] + body["attributes_skipped"]
        assert total_datasets == 5, f"Expected 5 node-label datasets: {body}"
        assert total_attrs == 20, f"Expected 20 property attribute links: {body}"
        assert body["errors"] == []

    @pytest.mark.crud
    def test_sync_is_idempotent(self, api):
        resp1 = api.post(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/sync-graph-attributes")
        resp2 = api.post(f"{BASE_URL}/api/data-products/{PRODUCT_ID}/sync-graph-attributes")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        b1, b2 = resp1.json(), resp2.json()
        # Totals must be equal across runs
        assert b1["datasets_created"] + b1["datasets_reused"] == b2["datasets_created"] + b2["datasets_reused"]
        assert b1["attributes_linked"] + b1["attributes_skipped"] == b2["attributes_linked"] + b2["attributes_skipped"]
        assert b2["errors"] == []

    @pytest.mark.crud
    def test_sync_missing_product_returns_400(self, api):
        resp = api.post(f"{BASE_URL}/api/data-products/00000000-0000-0000-0000-000000000000/sync-graph-attributes")
        assert resp.status_code in (400, 404)

    @pytest.mark.readonly
    def test_dataset_assets_exist_after_sync(self, api):
        resp = api.get(f"{BASE_URL}/api/assets", params={"platform": "Neo4j"})
        if resp.status_code == 404:
            pytest.skip("Assets endpoint not available")
        assert resp.status_code == 200
        body = resp.json()
        items = body if isinstance(body, list) else body.get("items", body.get("data", []))
        neo4j_assets = [a for a in items if a.get("platform") == "Neo4j"]
        assert len(neo4j_assets) >= 5, f"Expected ≥5 Neo4j Dataset assets, found {len(neo4j_assets)}"
        names = {a["name"] for a in neo4j_assets}
        assert {"Aircraft", "FlightLeg", "Alert", "MaintenanceEvent", "Incremental"} <= names


# ---------------------------------------------------------------------------
# 5. Regression: product update with null team field
# ---------------------------------------------------------------------------

class TestProductUpdateRegression:

    @pytest.mark.crud
    def test_update_product_with_null_team_does_not_500(self, api):
        """product_change_analyzer.py was crashing when team field is null."""
        resp = api.get(f"{BASE_URL}/api/data-products/{PRODUCT_ID}")
        assert resp.status_code == 200
        product = resp.json()
        assert product.get("team") is None  # Confirm null team scenario

        resp = api.put(
            f"{BASE_URL}/api/data-products/{PRODUCT_ID}",
            json=product,
        )
        assert resp.status_code == 200, f"PUT failed: {resp.status_code} {resp.text[:300]}"
