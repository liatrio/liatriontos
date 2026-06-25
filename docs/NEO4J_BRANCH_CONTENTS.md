# What's in feat/neo4j-data-product-v2

This branch has everything from `feat/neo4j-data-product` plus one commit on top that adds the host allowlist fix for the SSRF concern.

## Commits

Oldest first. Andrei's commits built the UI and graph visualization. My earlier commits set up the connector and docs. The last commit adds the security hardening.

```
8be38f12 Luis Vieira     - feat: add Neo4j Knowledge Graph connector and data product support
5d4fcb16 Luis Vieira     - docs: add quick start guide for new team members
9568cc92 Luis Vieira     - docs: add aggregate product type and placeholder host to YAML
f892bd63 atiterlea       - ODCS integration for Neo4j connector
c2baae87 atiterlea       - Fix performance issues
ec53441c atiterlea       - Improved visual representation of graph products
eebf9b1b atiterlea       - More performance tweaks
4728fbf8 atiterlea       - Updates to Data Product modal to allow creation of Knowledge Graph products
b0881593 atiterlea       - Added Neo4j PRD
3e856800 atiterlea       - Small fix for existing KG data product
a7d8753f atiterlea       - Generalizing Neo4j sink data product and updating PRD
9166e801 atiterlea       - Updated PRD
3c427450 Joao Luis Silva Vieira - fix: add Neo4j host allowlist to prevent SSRF via persisted config
```

## Files that matter

Backend:
- `src/backend/src/routes/neo4j_connector.py` — the API routes. Takes product_id, looks up config from DB, validates host against allowlist, connects.
- `src/backend/src/controller/neo4j_delivery_handler.py` — talks to Neo4j. Read-only queries, 10s timeout, 60s cache.
- `src/backend/src/app.py` — registers the neo4j router
- `src/backend/src/routes/__init__.py` — imports the module
- `src/backend/requirements.in` — has `neo4j>=5.0.0`

Frontend:
- `src/frontend/src/components/data-products/neo4j-graph-panel.tsx` — the Cytoscape graph visualization. Calls `/api/neo4j/{productId}/summary`, no creds sent.
- `src/frontend/src/views/data-product-details.tsx` — wires the panel into the product detail page
- `src/frontend/src/components/data-products/data-product-form-dialog.tsx` — Andrei's product creation modal with KG type

Docs:
- `docs/neo4j-kg-data-product-local.yaml` — sample product YAML for local testing
- `docs/neo4j-kg-data-contract.yaml` — ODCS contract for the graph schema
- `docs/LOCAL_DEV_SETUP.md` — how to run it

## How the security works

The API only takes a product ID. The backend reads the bolt URL from the product's output port in the database and checks it against `NEO4J_ALLOWED_HOSTS` (an env var set by whoever deploys the app). If the host isn't on the list, it returns 403 and never opens a connection.

Credentials come from Databricks UC Secrets — referenced by `secret_scope` and `secret_key` on the output port's custom properties. The actual password never appears in the YAML, the API request, or the API response.

In production without `NEO4J_ALLOWED_HOSTS` configured, everything is blocked. In local dev mode (`ENV=LOCAL`) without an allowlist, it lets anything through for convenience.

## Endpoints

```
GET /api/neo4j/{product_id}/health      — can we reach it?
GET /api/neo4j/{product_id}/metadata    — node labels, counts
GET /api/neo4j/{product_id}/freshness   — when was data last loaded?
GET /api/neo4j/{product_id}/summary     — all of the above
```

All require `data-products` READ_ONLY permission.
