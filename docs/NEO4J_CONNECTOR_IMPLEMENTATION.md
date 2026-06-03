# Neo4j Connector Implementation Guide

## Compatibility

**Base version:** `marketplace-v0.6.4` ([databrickslabs/ontos](https://github.com/databrickslabs/ontos/releases/tag/marketplace-v0.6.4))

This feature branch is fully compatible with the Databricks Marketplace release v0.6.4. All changes are additive — no existing files are modified in breaking ways.

## Verified E2E on marketplace-v0.6.4

Tested locally with:
- Backend: Python 3.10, FastAPI, SQLAlchemy + Lakebase (password auth)
- Frontend: Vite + React (yarn dev:frontend)
- Neo4j: bolt://oem-kg.neo4j.internal:7687 (user: neo4j, password: password)
- Data product imported via YAML upload through Ontos UI
- Knowledge Graph Summary panel renders live YAML in product detail view

### Branch setup

```bash
git clone https://github.com/databrickslabs/ontos.git
cd ontos
git checkout marketplace-v0.6.4 -b feat/neo4j-connector
# Apply the changes listed below
```

---

## Overview

This feature adds Neo4j Knowledge Graph integration to Ontos, enabling:
- Live graph metadata API (node counts, relationships, freshness)
- Registering Neo4j KGs as ODPS data products with management ports
- A frontend panel that renders the live graph state as YAML on the product detail page

---

## Files Added/Modified

### New Files

| File | Purpose |
|------|---------|
| `backend/src/controller/neo4j_delivery_handler.py` | Core handler — connects to Neo4j, extracts metadata, freshness, health |
| `backend/src/routes/neo4j_connector.py` | API routes: `/api/neo4j/{health,metadata,freshness,summary}` |
| `frontend/src/components/data-products/neo4j-graph-panel.tsx` | React component — renders live graph summary as YAML in product detail view |

### Modified Files

| File | Change |
|------|--------|
| `backend/src/routes/__init__.py` | Added `from . import neo4j_connector` |
| `backend/src/app.py` | Added `from src.routes.neo4j_connector import router as neo4j_router` and `app.include_router(neo4j_router)` (after the last `register_routes` call) |
| `frontend/src/views/data-product-details.tsx` | Imported `Neo4jGraphPanel` and inserted it after the Deliverables section |
| `requirements.in` | Added `neo4j>=5.0.0` |

---

## Setup Steps (Local Development)

### Prerequisites

- Python 3.10+
- Node.js 18+ with Yarn
- A reachable Neo4j instance (bolt protocol)
- Ontos backend running with PostgreSQL connection

> **No Neo4j instance available?** You can run one locally with Docker:
>
> ```bash
> docker run -d --name neo4j-local \
>   -p 7474:7474 -p 7687:7687 \
>   -e NEO4J_AUTH=neo4j/password \
>   neo4j:5-community
> ```
>
> Then use `bolt://localhost:7687` as your `bolt_url` in the YAML and API calls.
> The default credentials will be `neo4j` / `password`.

### 1. Install the Neo4j Python driver

```bash
cd src
.venv/bin/pip install 'neo4j>=5.0.0'
```

Or add to `requirements.in`:
```
neo4j>=5.0.0
```

### 2. Add the backend files

Copy these files into your Ontos source:

```
backend/src/controller/neo4j_delivery_handler.py
backend/src/routes/neo4j_connector.py
```

### 3. Register the route in `app.py`

Add after the last `register_routes(app)` call:

```python
# Neo4j Connector routes
from src.routes.neo4j_connector import router as neo4j_router
app.include_router(neo4j_router)
```

Also add the import in `backend/src/routes/__init__.py`:

```python
from . import neo4j_connector
```

### 4. Add the frontend component

Copy `neo4j-graph-panel.tsx` to:
```
frontend/src/components/data-products/neo4j-graph-panel.tsx
```

In `frontend/src/views/data-product-details.tsx`, add the import:

```tsx
import Neo4jGraphPanel from '@/components/data-products/neo4j-graph-panel';
```

And insert the component after the Deliverables `</Card>`:

```tsx
{/* Neo4j Knowledge Graph Summary (auto-detected from management ports) */}
<Neo4jGraphPanel managementPorts={product.managementPorts} />
```

### 5. Set Neo4j password (optional)

The handler reads `NEO4J_PASSWORD` from env vars. Default is `"password"`.

```bash
export NEO4J_PASSWORD=your_neo4j_password
```

### 6. Start the app

```bash
# Terminal 1 - Backend
cd src
PYTHONPATH=./backend .venv/bin/python backend/src/app.py

# Terminal 2 - Frontend
cd src/frontend
yarn dev:frontend
```

---

## API Endpoints

All endpoints require `bolt_url` as a query parameter.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/neo4j/health` | GET | Check connectivity to Neo4j |
| `/api/neo4j/metadata` | GET | Node labels, relationship types, counts |
| `/api/neo4j/freshness` | GET | Last-load dates from Incremental tracker node |
| `/api/neo4j/summary` | GET | Full summary (metadata + freshness + status) |

### Query Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `bolt_url` | required | Neo4j Bolt URL (e.g., `bolt://host:7687`) |
| `username` | `neo4j` | Neo4j username |
| `database` | `neo4j` | Neo4j database name |

### Example

```bash
curl 'http://localhost:8000/api/neo4j/summary?bolt_url=bolt://oem-kg.neo4j.internal:7687&database=neo4j'
```

### Response

```json
{
  "connected": true,
  "error": null,
  "database": "neo4j",
  "bolt_url": "bolt://oem-kg.neo4j.internal:7687",
  "graph": {
    "node_labels": ["MaintenanceEvent", "Part", "Aircraft", ...],
    "relationship_types": ["PART_HAS_SERIALIZED_INSTANCE", ...],
    "node_counts": {"MaintenanceEvent": 500, "Part": 104, ...},
    "relationship_counts": {"PART_HAS_SERIALIZED_INSTANCE": 5, ...},
    "total_nodes": 694,
    "total_relationships": 20
  },
  "freshness": {
    "shopfinding": "2026-05-28",
    "flightleg": "2026-05-28"
  }
}
```

---

## Creating a Neo4j Data Product

### Option 1: Import via YAML file (recommended)

Save the following as `neo4j-kg-data-product.yaml` and upload via the Ontos UI (**Data Products → Upload**):

```yaml
apiVersion: v1.0.0
kind: DataProduct

id: neo4j-kg-flight-ops
name: Flight Operations Knowledge Graph
version: "1.0.0"
status: active
domain: flight-operations
tenant: data-platform

description:
  purpose: >
    A Neo4j-backed knowledge graph that models relationships between aircraft,
    flight legs, alerts, and maintenance events.
  usage: >
    Explore connected flight operations data — trace alerts back to aircraft,
    flight legs, and maintenance actions.
  limitations: >
    Data freshness depends on the feeder engine schedule (daily batch).
    The graph is read-only.

outputPorts:
  - name: neo4j-graph-primary
    version: "1.0.0"
    description: Bolt connection to the Neo4j flight ops knowledge graph.
    port_type: neo4j-graph
    status: active
    contains_pii: false
    server:
      host: "bolt://<neo4j-host>:7687"
      database: "neo4j"

managementPorts:
  - name: neo4j-live-summary
    content: observability
    port_type: rest
    url: "http://<ontos-host>:8000/api/neo4j/summary?bolt_url=bolt://<neo4j-host>:7687&database=neo4j"
    description: Live graph metadata — node counts, relationships, freshness.

tags:
  - neo4j
  - knowledge-graph
  - flight-operations
  - derived-product
```

Replace `<neo4j-host>` and `<ontos-host>` with actual values. For local dev use `localhost`.

### Option 2: Import via API

```bash
curl -X POST http://localhost:8000/api/data-products/upload \
  -F "file=@neo4j-kg-data-product.yaml"
```

### Option 3: Create via API (JSON)

```bash
curl -X POST 'http://localhost:8000/api/data-products' \
  -H 'Content-Type: application/json' \
  -d '{
    "apiVersion": "v1.0.0",
    "kind": "DataProduct",
    "id": "neo4j-kg-flight-ops",
    "name": "Flight Operations Knowledge Graph",
    "version": "1.0.0",
    "status": "active",
    "domain": "flight-operations",
    "description": {
      "purpose": "Neo4j knowledge graph modeling aircraft, flights, alerts, and maintenance."
    },
    "output_ports": [{
      "name": "neo4j-graph-primary",
      "version": "1.0.0",
      "description": "Bolt connection to the Neo4j flight ops graph.",
      "port_type": "neo4j-graph",
      "status": "active",
      "contains_pii": false,
      "server": {
        "host": "bolt://oem-kg.neo4j.internal:7687",
        "database": "neo4j"
      }
    }],
    "management_ports": [{
      "name": "neo4j-live-summary",
      "content": "observability",
      "port_type": "rest",
      "url": "http://localhost:8000/api/neo4j/summary?bolt_url=bolt://oem-kg.neo4j.internal:7687&database=neo4j",
      "description": "Live graph metadata endpoint."
    }],
    "tags": ["neo4j", "knowledge-graph", "flight-operations"]
  }'
```

Once created, the product detail page will automatically detect the Neo4j management port and render the YAML summary panel.

### Importing the sample YAML file

A ready-to-use YAML file is included at `docs/neo4j-kg-data-product-local.yaml` with localhost URLs for local development.

---

## Frontend Widget Behavior

The `Neo4jGraphPanel` component:

1. Scans `managementPorts` for any port with `neo4j` in the URL or name
2. If found, fetches the URL on mount
3. Renders the response as a YAML-formatted code block showing:
   - Connection status
   - Node labels with counts
   - Relationship types with counts
   - Data freshness per feed
   - Bolt URL
4. Includes a refresh button for manual reload
5. Returns `null` (renders nothing) if no Neo4j management port exists

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────┐
│  Ontos Frontend     │────▶│  Ontos Backend   │────▶│   Neo4j     │
│  (React)            │     │  (FastAPI)       │     │  (Bolt)     │
│                     │     │                  │     │             │
│  neo4j-graph-panel  │     │  /api/neo4j/*    │     │  KG Data    │
│  renders YAML view  │     │  neo4j_connector │     │             │
└─────────────────────┘     └──────────────────┘     └─────────────┘
                                     │
                                     ▼
                            ┌──────────────────┐
                            │  PostgreSQL      │
                            │  (Lakebase)      │
                            │  stores product  │
                            │  metadata + mgmt │
                            │  port URLs       │
                            └──────────────────┘
```

---

## Deployment Notes

When deploying to Databricks Apps:
- The `neo4j>=5.0.0` dependency must be in `requirements.in` or `requirements.txt`
- The Neo4j instance must be network-reachable from the Databricks App (AKS internal DNS works if on the same VNet)
- The management port URL in the data product should point to the deployed app URL (not localhost)
- Neo4j password should be managed via env vars or Databricks Secrets (not hardcoded)

---

## Quick Start for New Team Members

If you're cloning this repo for the first time:

```bash
# 1. Clone the fork and checkout the branch
git clone https://github.com/liatrio/liatriontos.git
cd liatriontos
git checkout feat/neo4j-data-product

# 2. Set up Python environment
cd src
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install 'neo4j>=5.0.0'

# 3. (If no remote Neo4j) Start a local Neo4j container
docker run -d --name neo4j-local \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5-community

# 4. Configure your .env (copy from the Environment Configuration section below)
#    Key values to set:
#    - POSTGRES_HOST, POSTGRES_PASSWORD (for Lakebase)
#    - DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID
#    - NEO4J_PASSWORD=password

# 5. Start the backend
PYTHONPATH=./backend .venv/bin/python backend/src/app.py

# 6. In another terminal — start the frontend
cd src/frontend
yarn install
yarn dev:frontend

# 7. Test the Neo4j API
curl 'http://localhost:8000/api/neo4j/health?bolt_url=bolt://localhost:7687'

# 8. Import the sample data product
curl -X POST http://localhost:8000/api/data-products/upload \
  -F "file=@docs/neo4j-kg-data-product-local.yaml"
```

> **Note:** The sample YAML (`docs/neo4j-kg-data-product-local.yaml`) uses
> `bolt://oem-kg.neo4j.internal:7687` as the Neo4j host. If you're running
> Neo4j locally via Docker, edit the file and replace that with `bolt://localhost:7687`
> before importing.

---

## Known Limitations

- Neo4j password is read from `NEO4J_PASSWORD` env var (no secrets integration yet)
- No authentication on the `/api/neo4j/*` endpoints (relies on app-level auth)
- Frontend panel does a direct fetch to the management port URL (CORS must be configured if cross-origin)
- The freshness data depends on the feeder engine writing an `(:Incremental)` node

---

## Environment Configuration

Add these to your `backend/.env` file for local development:

```bash
# --- General ---
ENV=LOCAL
DEBUG=True
LOG_LEVEL=INFO

APP_DEMO_MODE=False
APP_DB_DROP_ON_START=False
APP_DB_ECHO=False

# --- Databricks Connection ---
DATABRICKS_HOST=https://adb-<workspace-id>.<region>.azuredatabricks.net
DATABRICKS_WAREHOUSE_ID=<your-warehouse-id>
DATABRICKS_CATALOG=app_data_dev
DATABRICKS_SCHEMA=app_ontos_dev
DATABRICKS_VOLUME=app_files_dev
APP_AUDIT_LOG_DIR=audit_logs

# --- PostgreSQL (Lakebase) ---
POSTGRES_HOST=<your-lakebase-endpoint>.database.eastus.azuredatabricks.net
POSTGRES_PORT=5432
POSTGRES_USER=username
POSTGRES_PASSWORD=<your-lakebase-password>
POSTGRES_DB=databricks_postgres
DB_SCHEMA=app_ontos
DB_USE_PASSWORD_AUTH=true

# --- RBAC ---
APP_ADMIN_DEFAULT_GROUPS=["admins"]

# --- LLM (optional) ---
LLM_ENABLED=False

# --- Neo4j (for the connector) ---
NEO4J_PASSWORD=password
```

For production deployment, replace:
- `POSTGRES_HOST` with your Lakebase autoscale endpoint
- `DATABRICKS_HOST` with your workspace URL
- `NEO4J_PASSWORD` with the actual Neo4j credentials (or use Databricks Secrets)

---

## ODPS Data Product YAML

This YAML defines the Neo4j Knowledge Graph as a data product following ODPS v1.0.0:

```yaml
# neo4j-knowledge-graph-data-product.yaml
---
apiVersion: v1.0.0
kind: DataProduct

id: neo4j-knowledge-graph-flight-ops
name: Flight Operations Knowledge Graph
version: "1.0.0"
status: active
domain: flight-operations
tenant: data-platform

description:
  purpose: >
    A Neo4j-backed knowledge graph that models relationships between aircraft,
    flight legs, alerts, and maintenance events. Derived from Databricks tables
    and fed via the neo4j-feeder-engine ETL pipeline.
  usage: >
    Use this data product to explore connected flight operations data —
    trace alerts back to specific aircraft, flight legs, and maintenance actions.
    Suitable for graph-based queries, path analysis, and relationship discovery.
  limitations: >
    Data freshness depends on the feeder engine schedule (currently daily batch).
    The graph is read-only; writes go through the ETL pipeline only.

outputPorts:
  - name: neo4j-graph-primary
    version: "1.0.0"
    description: >
      Primary graph output — bolt connection to the Neo4j database containing
      flight operations knowledge graph data.
    port_type: neo4j-graph
    status: active
    contains_pii: false
    auto_approve: false
    server:
      bolt_url: "bolt://<neo4j-host>:7687"
      database: "neo4j"
      neo4j_labels:
        - Aircraft
        - FlightLeg
        - Alert
        - MaintenanceEvent
        - Incremental
      neo4j_relationships:
        - OPERATED
        - TRIGGERED
        - RESOLVED_BY
        - TRACKED_BY

managementPorts:
  - name: neo4j-live-summary
    content: observability
    port_type: rest
    url: "https://<ontos-app-host>/api/neo4j/summary?bolt_url=bolt://<neo4j-host>:7687&database=neo4j"
    description: >
      Live API endpoint that returns graph metadata (node counts, relationship types),
      data freshness per feed, and connectivity status. Called by the Ontos product
      detail view to display real-time graph info.

  - name: neo4j-health-check
    content: observability
    port_type: rest
    url: "https://<ontos-app-host>/api/neo4j/health?bolt_url=bolt://<neo4j-host>:7687&database=neo4j"
    description: >
      Health check endpoint — validates connectivity to the Neo4j instance.

  - name: neo4j-metadata
    content: discoverability
    port_type: rest
    url: "https://<ontos-app-host>/api/neo4j/metadata?bolt_url=bolt://<neo4j-host>:7687&database=neo4j"
    description: >
      Returns node labels, relationship types, and counts for graph exploration.

  - name: neo4j-freshness
    content: observability
    port_type: rest
    url: "https://<ontos-app-host>/api/neo4j/freshness?bolt_url=bolt://<neo4j-host>:7687&database=neo4j"
    description: >
      Returns last-load dates per feed from the Incremental tracker node.

team:
  name: Data Intelligence Platform
  members:
    - username: team-lead@example.com
      name: Team Lead
      role: owner

support:
  - channel: teams-data-platform
    url: "https://teams.microsoft.com/l/channel/data-platform"
    tool: teams
    scope: interactive
    description: Data platform team channel for questions and support

tags:
  - neo4j
  - knowledge-graph
  - flight-operations
  - derived-product
```

Replace `<neo4j-host>` and `<ontos-app-host>` with your actual hostnames before importing.
