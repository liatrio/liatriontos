# PRD: Knowledge Graph Connector — Neo4j Data Products

## Problem Statement

Ontos manages Data Products backed by Databricks Unity Catalog assets (tables, views, models). **Neo4j Knowledge Graphs are an important and underserved product type**: they are populated by ETL engines that pull from Databricks and build relationship-rich representations of operational data, yet Ontos has no way to register or govern them. Specifically:

1. **No product type for graph databases.** The ODPS `productType` vocabulary covers `source`, `source-aligned`, `aggregate`, `consumer-aligned`, and `sink`, but not Knowledge Graph. There is no way for a Data Producer to register a Neo4j database as a first-class data product.
2. **No live graph metadata surface.** Even if a product is registered, there is no way to inspect what node labels, relationship types, row counts, or data freshness exist inside the graph without leaving Ontos and connecting directly to Neo4j.
3. **No graph visualization.** Static YAML or table representations are inadequate for a graph product — consumers need to see the schema topology (node → relationship → node) to evaluate whether the product meets their needs.
4. **No secret management for graph credentials.** Neo4j instances require a Bolt URL, username, and password. There is no mechanism to store credentials securely alongside the product definition — passing raw passwords in the UI is not acceptable in production.
5. **No catalog representation of graph entities.** The node labels inside a Neo4j graph (e.g., `Aircraft`, `FlightLeg`, `Alert`) are logical datasets with properties. They are invisible to Ontos's asset catalog, making governance and lineage impossible.

On the frontend, **list-endpoint performance** for Data Products and Data Contracts was degraded (~2.6 s each) due to N+1 SQLAlchemy query patterns triggered by lazy-loaded relationships and sequential per-row database round-trips — an unrelated but blocking issue for any meaningful use of the product list pages.

## Solution

### `knowledge-graph` Product Type

A new product type value `knowledge-graph` is added to the ODPS `productType` vocabulary in Ontos. Selecting it in the create/edit dialog reveals a dedicated connection configuration section for the Neo4j instance. The panel on the product details page is gated on this type — no other product type renders the graph UI.

### Neo4j Connector Backend

Four read-only API endpoints are exposed under `/api/neo4j/`:

| Endpoint | Purpose |
|---|---|
| `GET /api/neo4j/health` | Connectivity check — returns `connected`, `bolt_url`, `database` |
| `GET /api/neo4j/metadata` | Graph schema — node labels, relationship types, counts, topology edges |
| `GET /api/neo4j/freshness` | Data freshness per feed from the `Incremental` tracker node |
| `GET /api/neo4j/summary` | Unified response combining metadata + freshness + connectivity status |

All endpoints accept `bolt_url`, `username`, `database`, `secret_scope`, and `secret_key` as query parameters. The `summary` endpoint is the one called by the frontend panel. The handler (`Neo4jDeliveryHandler`) opens a Bolt session, fires three read-only Cypher queries (node counts, relationship counts, topology), reads the `Incremental` tracker node for freshness, and closes the connection on every request — no persistent connection pool.

### Databricks UC Secret Scope Authentication

Neo4j passwords are resolved at request time from a **Databricks Unity Catalog Secret Scope**, not stored in the database. The backend resolves the password via `ws.secrets.get_secret(scope, key)` injected through the existing `WorkspaceClientDep` dependency. Falls back to the `NEO4J_PASSWORD` environment variable for local development. This follows the same pattern already established by the BigQuery connector.

The secret scope name and key are stored as `customProperties` on the management port — `secret_scope` and `secret_key` — alongside `username` and `database`. The actual password never touches the Ontos database or the frontend.

### Knowledge Graph Management Port Convention

A `knowledge-graph` product's Neo4j connection is stored as a management port with `content: "observability"` and `type: "rest"`. The `url` field holds the **Bolt URL** of the Neo4j instance (e.g., `bolt://my-neo4j:7687`). The frontend panel reads the Bolt URL from this port and constructs the backend API call `/api/neo4j/summary?bolt_url=...&username=...&secret_scope=...&secret_key=...` at render time. There is no hardcoded naming convention on the port — it is identified by being the first management port with a non-empty URL, which is unambiguous for `knowledge-graph` products.

### Cytoscape.js Graph Visualization Panel

A new frontend component, `Neo4jGraphPanel`, renders the graph topology as an interactive node-link diagram using **Cytoscape.js** (already installed in the project as `react-cytoscapejs`). It replaces a prior text/YAML display and matches the visual language of the Concepts dashboard's graph view.

Features:
- **Node layout switcher**: Hierarchical (breadthfirst, default), Circular, Force-Directed (CoSE), Concentric
- **Zoom controls**: zoom in, zoom out, fit to canvas, reset layout
- **Fullscreen dialog**: expands to 95 vw × 90 vh with the same controls and a second independent Cytoscape instance
- **Dark mode awareness**: stylesheet tracks `document.documentElement.classList` via `MutationObserver`
- **Node tooltips on hover**: nodes grow and highlight; edges change color on hover
- **Header metadata**: database name, connection status indicator, total node count, total relationship count, per-feed freshness dates

The panel only mounts and fetches when the product type is `knowledge-graph` and a management port with a URL is present; it returns `null` for all other products.

### `sync-graph-attributes` — Catalog Integration

A new endpoint `POST /api/data-products/{id}/sync-graph-attributes` introspects the live Neo4j graph and creates **Dataset assets** in the Ontos asset catalog — one per node label — with logical attribute links for each property found on that label's nodes. The operation is idempotent: existing datasets and attributes are reused, and only new ones are created. The response reports counts of `datasets_created`, `datasets_reused`, `attributes_linked`, `attributes_skipped`, and any `errors`.

### Data Product & Contract List Performance Fixes

The `~2.6 s` list-endpoint latency was caused by two N+1 patterns:

1. **Data Contracts** (`list_contracts_from_db`): five sequential batch queries (domain names, team names, project names, schema counts) replaced with a single `LEFT JOIN` query grouping by contract ID.
2. **Data Products** (`get_multi`): six unused SQLAlchemy `selectin` relationships (description, authoritative definitions, custom properties, input ports, management ports, support channels) replaced with `noload()` options to suppress auto-firing.
3. **Authorization** (`get_user_team_role_overrides`): four sequential queries per request replaced with a single `TeamMemberDb IN` query.

### Data Contract Details — Inline Schema Properties

The schema properties tab in Data Contract Details was firing a separate `/schemas/{name}/properties` API call per schema on every expand. For contracts with fewer than 50 properties per schema (the common case), properties are now read from the inline `schema.properties` array returned by the initial contract GET, eliminating the extra round-trip entirely.

## User Stories

1. As a **Data Producer**, I want to select "Knowledge Graph" as my product type when creating a new data product, so that I can register a Neo4j database as a first-class Ontos product.
2. As a **Data Producer**, I want to enter the Neo4j Bolt URL, username, database name, and Databricks secret scope/key in the create dialog, so that the product stores enough information to connect to the graph at runtime.
3. As a **Data Producer**, I want the Neo4j connection fields to only appear when I select "Knowledge Graph" as the product type, so that the form is not cluttered for other product types.
4. As a **Data Consumer**, I want to see a live interactive graph topology on the Knowledge Graph product details page, so that I can understand the schema structure without leaving Ontos.
5. As a **Data Consumer**, I want to switch between Hierarchical, Circular, Force-Directed, and Concentric layouts, so that I can find the view that best reveals the graph's structure.
6. As a **Data Consumer**, I want to zoom, pan, and fit the graph to the canvas, so that I can navigate large schemas.
7. As a **Data Consumer**, I want to open a fullscreen view of the graph, so that I can inspect dense topologies without the space constraint of the panel card.
8. As a **Data Consumer**, I want to see the data freshness per feed (e.g., when `FlightLeg` was last loaded) alongside the graph, so that I can assess the timeliness of the product.
9. As a **Data Consumer**, I want the graph panel to adapt to dark mode automatically, so that it remains readable regardless of my UI theme preference.
10. As a **Data Producer**, I want the Neo4j password to be resolved from a Databricks UC Secret Scope at request time, so that credentials are never stored in the Ontos database.
11. As a **Platform Engineer**, I want to fall back to a `NEO4J_PASSWORD` environment variable during local development, so that secret scope configuration is not required to run the app locally.
12. As a **Data Producer**, I want to run `sync-graph-attributes` to automatically register Neo4j node labels as Dataset assets in the Ontos catalog, so that they participate in governance workflows (tagging, lineage, reviews).
13. As a **Data Producer**, I want `sync-graph-attributes` to be idempotent, so that I can re-run it safely after the graph schema changes without creating duplicate catalog entries.
14. As a **Data Steward**, I want Knowledge Graph node labels to appear as Dataset assets in the Asset Explorer with their logical attributes, so that I can apply tags, quality rules, and governance policies to graph entities.
15. As a **Data Consumer**, I want the Data Product list page to load in under 500 ms, so that discovery is not blocked by slow API responses.
16. As a **Data Consumer**, I want the Data Contracts list page to load in under 500 ms, so that browsing available contracts is fast.
17. As a **Data Producer**, I want the schema properties tab on a Data Contract to open instantly for small schemas, so that I am not blocked waiting for a redundant network call.
18. As a **Data Consumer**, I want the graph panel to show a clear error message if the Neo4j instance is unreachable, so that I know the product has a connectivity issue rather than seeing a crash.

## Implementation Decisions

### New Modules

- **`Neo4jDeliveryHandler`** (`src/backend/src/controller/neo4j_delivery_handler.py`): Stateless handler. Constructor takes `bolt_url`, `username`, `password`, `database`. Methods: `health_check()`, `get_graph_metadata()` → `Neo4jGraphMetadata`, `get_freshness()` → `dict[str, str]`, `get_product_summary()` → `dict`. Opens a new Bolt session per method call via `neo4j.GraphDatabase.driver`. The driver itself is lazy-initialized on first use and closed explicitly by the route handler via `.close()`.
- **`Neo4jGraphPanel`** (`src/frontend/src/components/data-products/neo4j-graph-panel.tsx`): Self-contained React component. Props: `managementPorts?: ManagementPort[]`, `productType?: string`. Returns `null` unless `productType === 'knowledge-graph'` and at least one management port has a URL. Owns its own fetch, layout, and fullscreen state.
- **E2E test suite** (`src/e2e/tests/test_neo4j_connector.py`): Covers Neo4j endpoint correctness, data product readiness checks, `sync-graph-attributes` idempotency, and the null-team regression.

### API Design

All four endpoints accept the same five query parameters:

| Parameter | Required | Default | Notes |
|---|---|---|---|
| `bolt_url` | Yes | — | Neo4j Bolt URL |
| `username` | No | `neo4j` | Neo4j username |
| `database` | No | `neo4j` | Neo4j database name |
| `secret_scope` | No | — | Databricks UC Secret scope |
| `secret_key` | No | — | Key within the secret scope |

If `secret_scope` and `secret_key` are both provided, the password is resolved via the Databricks SDK. If either is absent, `NEO4J_PASSWORD` env var is used. An HTTP 500 is returned if secret resolution fails (scope/key provided but secret not found or SDK error).

The topology query returns `(from_label)-[rel_type]->(to_label)` triples with counts, which the frontend uses to build Cytoscape edge elements. Labels with no relationships still appear as nodes (from the node count query).

### Authentication Flow

```
Frontend panel
  → reads neo4jPort.url (Bolt URL), customProperties[secret_scope], customProperties[secret_key]
  → constructs: GET /api/neo4j/summary?bolt_url=...&secret_scope=...&secret_key=...
Backend route
  → injects WorkspaceClientDep (existing singleton)
  → calls ws.secrets.get_secret(scope=secret_scope, key=secret_key).value
  → base64-decodes if necessary (Databricks REST API encodes secret bytes)
  → passes plaintext password to Neo4jDeliveryHandler constructor
  → handler opens Bolt session, queries, closes
```

No password is logged, persisted, or returned in any API response.

### Cytoscape Element Construction

Nodes are built from `graph.node_labels` (one node per label, colored from a fixed 12-color palette by index). Edges are built from `graph.topology` entries. Both node and edge elements carry `data` payloads for labels, counts, and freshness. The layout is run after mount via a `setTimeout(80ms)` delay to ensure Cytoscape has a concrete pixel height before measuring.

Two independent Cytoscape instances are maintained — one for the inline panel (fixed `height: 680px`) and one for the fullscreen dialog (`flex-1 min-h-0`) — each with its own `cy` ref and `runLayout` call. This avoids the complexity of re-parenting a single instance across DOM trees.

### Performance Fix Strategy

The N+1 patterns were all rooted in SQLAlchemy's `lazy="selectin"` default on relationships, which fires one `IN` query per relationship per `get_multi()` call over a remote PostgreSQL instance (~190 ms per round-trip). The fix strategy is:

- **Suppress unused relationships** via `noload()` at query time — zero extra queries for columns that the list view never renders.
- **Collapse sequential lookups into JOIN** for the contract list — one query instead of five.
- **Replace per-request team iteration** in `PermissionChecker` with a single `TeamMemberDb IN` filter.

These are targeted changes to query options and one query rewrite; no schema migrations, no index changes, and no application-level caching was added.

### Error Handling

- **Neo4j unreachable**: `Neo4jDeliveryHandler` catches `ServiceUnavailable` and `AuthError`, returns a `connected: False` response body with an `error` string. The `/summary` endpoint never returns a non-200 status for connectivity failures — the panel handles the `connected: false` payload gracefully.
- **Secret resolution failure**: Returns HTTP 500 with a detail message. This is the only case where the endpoint raises `HTTPException` — it is a configuration error, not a graph error.
- **No management port URL**: Panel returns `null` silently.
- **Empty graph** (zero nodes): Panel shows the controls bar but no Cytoscape canvas (elements array is empty; the `elements.length > 0` guard skips rendering).

### `sync-graph-attributes` Design

The endpoint calls `get_graph_metadata()` to retrieve node labels and their property keys, then:
1. Looks up or creates a Dataset asset per node label (platform: `"Neo4j"`)
2. Looks up or creates a logical attribute per property key
3. Links the attribute to the dataset via `EntityRelationshipDb`

All DB operations use the existing `AssetsManager` and repository pattern. The response body is a summary dict — not the created entities — to keep the payload small for large graphs.

## Testing Decisions

### E2E Tests (`test_neo4j_connector.py`)

The suite uses a `requests.Session` against the local dev server (port 8000) and auto-skips when the server or Neo4j is unreachable. Tests are organized into five classes:

- **`TestBackendHealth`**: Smoke test verifying DB + workspace client connectivity. Prerequisite for all others.
- **`TestNeo4jEndpoints`**: Correctness of all four API endpoints. Asserts on specific node labels and relationship types from the Flight Operations demo graph. Asserts that unreachable Bolt URLs return `connected: false` (not HTTP 500).
- **`TestDataProductReadiness`**: Verifies that the demo Knowledge Graph product passes ODPS metadata, output port contract, logical attribute, and business lineage readiness checks.
- **`TestSyncGraphAttributes`**: Verifies that `sync-graph-attributes` returns the expected dataset and attribute counts, and that two consecutive runs produce identical totals (idempotency).
- **`TestProductUpdateRegression`**: Regression test for the null-team `product_change_analyzer.py` crash — fetches the product (which has no team) and PUTs it back, expecting HTTP 200.

Tests are marked with `smoke`, `readonly`, or `crud` for selective execution in CI.

### What Is Not Tested

- Cytoscape rendering correctness — layout algorithms and visual output are not verifiable in Jest without a canvas environment.
- Secret scope resolution in CI — requires a live Databricks workspace. Covered by the env var fallback path in integration tests.

## Out of Scope

- **Write operations to Neo4j** — creating nodes, relationships, or indexes from Ontos. This is a delivery-time concern handled by the feeder engine (ETL pipeline), not the catalog app.
- **Neo4j connection pooling** — the handler opens and closes a Bolt session per API call. Connection pooling (e.g., a singleton driver per configured instance) is a v2 concern; at present, summary calls are user-triggered and infrequent.
- **Multiple Neo4j instances per product** — a `knowledge-graph` product has exactly one management port with a Bolt URL. Supporting multiple instances (e.g., one per environment) is deferred.
- **Cypher query execution from the UI** — ad-hoc querying against the graph is out of scope. The panel is read-only metadata only.
- **UC Connections for Neo4j** — Unity Catalog's external connections API does not support Neo4j at the time of writing. Secret Scopes are the correct mechanism.
- **Automated freshness alerting** — detecting stale feeds and notifying owners is a separate concern belonging to the Compliance feature.
- **Row-level graph data preview** — showing actual node properties or relationship payloads (as opposed to schema/topology) is a v2 feature.

## Further Notes

### Implementation Phases

1. **Backend connector** — `Neo4jDeliveryHandler`, four API routes, secret resolution, router registration. Prerequisite for all frontend work.
2. **Product type + connection form** — `knowledge-graph` type in the create dialog, Neo4j connection fields, management port storage convention.
3. **Graph panel** — `Neo4jGraphPanel` component, Cytoscape layout switcher, fullscreen dialog, dark mode support. Integration into `data-product-details.tsx`.
4. **Catalog sync** — `sync-graph-attributes` endpoint, Dataset asset creation, attribute linking.
5. **Performance fixes** — `noload()` on unused relationships, JOIN rewrite for contract list, authorization query collapse. These are independent of the graph feature and can be merged separately.
6. **E2E tests** — Written against the Flight Operations demo product; require a local Neo4j instance seeded with the demo graph.

### Relationship to Existing Features

- **Management Ports (ODPS)**: The Neo4j connection is stored as a management port with `content: "observability"`. This is consistent with the ODPS specification's intent for management ports — operational endpoints for monitoring and observability of the product's infrastructure. No new database columns or schema changes are required.
- **Asset Explorer / `sync-graph-attributes`**: Node labels registered by the sync endpoint appear as `asset_type="Dataset"` entities in the Asset Explorer, following the same ontology-driven pattern as manually-created datasets. They participate in the same review, tagging, and governance workflows.
- **Cytoscape.js (Concepts dashboard)**: The graph panel reuses `react-cytoscapejs` and `cytoscape`, already installed for the Concepts dashboard's knowledge graph view (`knowledge-graph.tsx`). The stylesheet and layout API are deliberately consistent with that component so the two graph surfaces feel like one visual system.
- **BigQuery Connector**: The secret resolution pattern in `neo4j_connector.py` (`get_secret` → base64 decode → fallback to env var) is identical to the pattern in `src/backend/src/connectors/bigquery.py`. Any future connector should follow this same pattern.
