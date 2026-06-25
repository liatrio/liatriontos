# Running liatriontos feat/neo4j-data-product-v2 locally

## Prerequisites

- Docker
- Node.js 18+ (tested with 26)
- Python 3.11+ (hatch will install 3.11 automatically)
- yarn

## 1. Clone and checkout

```bash
git clone https://github.com/liatrio/liatriontos.git
cd liatriontos
git checkout feat/neo4j-data-product-v2
```

## 2. Start Docker containers

```bash
docker run -d --name ontos-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:5-community
docker run -d --name ontos-postgres -p 5432:5432 -e POSTGRES_USER=ontos -e POSTGRES_PASSWORD=ontos -e POSTGRES_DB=ontos postgres:15-alpine
```

## 3. Seed Neo4j with sample data

```bash
docker exec ontos-neo4j cypher-shell -u neo4j -p password "
CREATE (a1:Aircraft {registration: 'N12345', type: 'B737-800'})
CREATE (a2:Aircraft {registration: 'N67890', type: 'B787-9'})
CREATE (a3:Aircraft {registration: 'N11111', type: 'A320neo'})
CREATE (m1:MaintenanceEvent {eventId: 'ME-001', eventType: 'engine_vibration', severity: 'high', description: 'Engine 1 vibration exceeded threshold'})
CREATE (m2:MaintenanceEvent {eventId: 'ME-002', eventType: 'brake_wear', severity: 'medium', description: 'Left main gear brake wear limit'})
CREATE (m3:MaintenanceEvent {eventId: 'ME-003', eventType: 'engine_vibration', severity: 'high', description: 'Engine 2 vibration spike during climb'})
CREATE (m4:MaintenanceEvent {eventId: 'ME-004', eventType: 'hydraulic_leak', severity: 'critical', description: 'Hydraulic system A pressure drop'})
CREATE (fl1:FlightLeg {legId: 'FL-1001', origin: 'SEA', destination: 'LAX', date: '2026-06-20'})
CREATE (fl2:FlightLeg {legId: 'FL-1002', origin: 'LAX', destination: 'JFK', date: '2026-06-21'})
CREATE (fl3:FlightLeg {legId: 'FL-1003', origin: 'SEA', destination: 'ORD', date: '2026-06-22'})
CREATE (al1:Alert {alertId: 'ALT-001', type: 'IFSD', severity: 'critical', message: 'In-flight shutdown engine 1'})
CREATE (al2:Alert {alertId: 'ALT-002', type: 'MAINT_DUE', severity: 'medium', message: 'Scheduled maintenance overdue'})
CREATE (inc:Incremental {schema: 'V3', flightlegs: '2026-06-22', alerts: '2026-06-22', maintenance: '2026-06-21'})
CREATE (a1)-[:OPERATED]->(fl1)
CREATE (a1)-[:OPERATED]->(fl2)
CREATE (a2)-[:OPERATED]->(fl3)
CREATE (a1)-[:HAS_MAINTENANCE_EVENT]->(m1)
CREATE (a1)-[:HAS_MAINTENANCE_EVENT]->(m2)
CREATE (a2)-[:HAS_MAINTENANCE_EVENT]->(m3)
CREATE (a3)-[:HAS_MAINTENANCE_EVENT]->(m4)
CREATE (fl1)-[:TRIGGERED]->(al1)
CREATE (fl2)-[:TRIGGERED]->(al2)
CREATE (al1)-[:RESOLVED_BY]->(m1)
CREATE (al2)-[:RESOLVED_BY]->(m2)
RETURN 'Done' AS result
"
```

## 4. Configure backend .env

Create `src/backend/.env`:

```bash
ENV=LOCAL
DEBUG=True
LOG_LEVEL=INFO
APP_DEMO_MODE=False
APP_DB_DROP_ON_START=True
APP_DB_ECHO=False

DATABRICKS_HOST=https://adb-placeholder.azuredatabricks.net
DATABRICKS_TOKEN=dapi-placeholder
DATABRICKS_WAREHOUSE_ID=placeholder
DATABRICKS_CATALOG=app_data_dev
DATABRICKS_SCHEMA=app_ontos_dev
DATABRICKS_VOLUME=app_files_dev
APP_AUDIT_LOG_DIR=audit_logs

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=ontos
POSTGRES_PASSWORD=ontos
POSTGRES_DB=ontos
DB_SCHEMA=public
DB_USE_PASSWORD_AUTH=true

APP_ADMIN_DEFAULT_GROUPS=["admins"]
LLM_ENABLED=False

NEO4J_PASSWORD=password
NEO4J_ALLOWED_HOSTS=localhost,neo4j-host.internal
```

## 5. Start the backend

```bash
cd src
pip install hatch  # if not installed
hatch -e dev run pip install neo4j  # first time only
NEO4J_PASSWORD=password NEO4J_ALLOWED_HOSTS=localhost,neo4j-host.internal ENV=LOCAL hatch -e dev run dev-backend
```

Wait until you see `Application startup complete`.

## 6. Upload the data product

```bash
curl -s -X POST http://localhost:8000/api/data-products/upload \
  -F "file=@docs/neo4j-kg-data-product-local.yaml"
```

Note the product ID from the response.

## 7. Set the server field on the output port

The YAML importer doesn't persist the `server` field. Set it manually:

```bash
docker exec ontos-postgres psql -U ontos -d ontos -c \
  "UPDATE data_product_output_ports SET server = '{\"host\": \"bolt://localhost:7687\", \"database\": \"neo4j\"}', port_type = 'neo4j-graph' WHERE name = 'neo4j-graph-primary';"
```

## 8. Verify the backend

```bash
curl -s http://localhost:8000/api/neo4j/<product_id>/summary | python3 -m json.tool
```

Should return node counts, relationships, topology, and freshness.

## 9. Start the frontend

```bash
cd src/frontend
yarn install  # first time
yarn dev:frontend
```

Open http://localhost:3000, navigate to the product, and the Knowledge Graph panel renders.

## Known issues

- **Linking a contract wipes the server field.** The Ontos product update logic replaces output port records, losing `server` and `port_type`. After linking a contract, re-run step 7.
- **YAML import doesn't persist `server`.** Always set it manually after import (step 7).
- **`APP_DB_DROP_ON_START=True`** recreates tables on every restart. Set to `False` after first run to keep data.
- **`neo4j` not in hatch dev env by default.** The `pyproject.toml` dev dependencies don't include `neo4j`. Run `hatch -e dev run pip install neo4j` after hatch creates the env (first time only). To make it permanent, add `"neo4j>=5.0.0"` to the `[tool.hatch.envs.dev] dependencies` list in `src/pyproject.toml`.
- **`yarn install` may fail with Node 26+.** Some transitive deps (`fdir`) have compatibility issues with Node 26. If `yarn install` fails, try `npm install` instead, or use Node 24 (check `.node-version` file). As a workaround you can symlink `node_modules` from a working Ontos checkout if the package versions match.
- **`npx vite` instead of `yarn dev:frontend`.** If yarn scripts don't resolve `vite`, use `npx vite` directly from the `src/frontend` directory.

## Stopping

```bash
docker stop ontos-neo4j ontos-postgres
docker rm ontos-neo4j ontos-postgres
```
