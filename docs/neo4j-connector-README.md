# Neo4j Connector for Ontos — Derived Data Products

## Overview

This feature extends Ontos to support **Neo4j Knowledge Graphs as derived data products** in the data mesh. It enables discovery, metadata extraction, and freshness monitoring for graph-based data products alongside native Databricks assets.

### Problem

Ontos currently supports source-aligned data products (Databricks catalogs with medallion schemas). However, application teams consume data through derivative systems like Neo4j Knowledge Graphs. These derived products have no representation in the data catalog — making them invisible to discovery.

### Solution

A Neo4j connector that:
- Queries live Neo4j instances for graph metadata (node labels, relationship types, counts)
- Reports data freshness per feed from the incremental tracker
- Exposes this metadata via API for the Ontos product detail view
- Extends the ODPS model to represent graph-specific output ports

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Ontos UI                           │
│  Product Detail → Neo4j Graph Panel                  │
└──────────────────────┬───────────────────────────────┘
                       │ GET /api/neo4j/summary
                       ▼
┌──────────────────────────────────────────────────────┐
│              Ontos Backend (FastAPI)                  │
│  routes/neo4j_connector.py                           │
│  controller/neo4j_delivery_handler.py                │
└──────────────────────┬───────────────────────────────┘
                       │ bolt://
                       ▼
┌──────────────────────────────────────────────────────┐
│              Neo4j (AKS)                             │
│  OEM STC Knowledge Graph                             │
│  694 nodes · 20 relationships · 16 labels            │
└──────────────────────────────────────────────────────┘
```

---

## Files Changed

| File | Type | Purpose |
|------|------|---------|
| `src/backend/src/controller/neo4j_delivery_handler.py` | New | Core handler — health_check, get_graph_metadata, get_freshness, get_product_summary |
| `src/backend/src/routes/neo4j_connector.py` | New | API routes: `/api/neo4j/{health,metadata,freshness,summary}` |
| `src/backend/src/models/data_products.py` | Modified | Extended `Server` model with `bolt_url`, `neo4j_database`, `neo4j_labels`, `neo4j_relationships` |
| `src/backend/src/controller/delivery_service.py` | Modified | Added `NEO4J_EXPORT` and `NEO4J_METADATA_SYNC` to `DeliveryChangeType` |
| `src/backend/src/routes/__init__.py` | Modified | Registered neo4j_connector route module |
| `src/frontend/src/components/data-products/neo4j-graph-panel.tsx` | New | React component for displaying graph metadata in product detail view |
| `src/requirements.in` | Modified | Added `neo4j>=5.0.0` |

---

## API Endpoints

### `GET /api/neo4j/health`
Check connectivity to a Neo4j instance.

**Parameters:** `bolt_url` (required), `username`, `database`

**Response:**
```json
{"connected": true, "bolt_url": "bolt://host:7687", "database": "neo4j"}
```

### `GET /api/neo4j/metadata`
Get graph metadata — node labels, relationship types, and counts.

**Response:**
```json
{
  "node_labels": ["FlightLeg", "Alert", "Fault", "Aircraft", ...],
  "relationship_types": ["FAULT_OCCURRED_DURING_FLIGHTLEG", ...],
  "node_counts": {"FlightLeg": 5, "Alert": 5, ...},
  "total_nodes": 694,
  "total_relationships": 20
}
```

### `GET /api/neo4j/freshness`
Get data freshness per feed from the Incremental tracker node.

**Response:**
```json
{
  "flightleg": "2026-05-28",
  "alert": "2026-05-28",
  "fault": "2026-05-28",
  "componentremoval": "2026-05-28"
}
```

### `GET /api/neo4j/summary`
Full product summary combining metadata + freshness + connectivity status.

---

## Data Model Extension

### Server Model (OutputPort)

Added fields to `Server` in `models/data_products.py`:

```python
bolt_url: Optional[str]           # "bolt://host:7687"
neo4j_database: Optional[str]     # defaults to "neo4j"
neo4j_labels: Optional[str]       # comma-separated node labels
neo4j_relationships: Optional[str] # comma-separated relationship types
```

### DeliveryChangeType

Added delivery types for Neo4j operations:

```python
NEO4J_EXPORT = "neo4j_export"
NEO4J_METADATA_SYNC = "neo4j_metadata_sync"
```

---

## Frontend Component

`neo4j-graph-panel.tsx` renders:
- Connection status (green/red indicator)
- Node labels as badges with counts
- Relationship types as badges with counts
- Data freshness grid (feed → last load date)
- Total nodes/relationships summary

### Usage in product detail view:

```tsx
{outputPort.server?.bolt_url && (
  <Neo4jGraphPanel
    boltUrl={outputPort.server.bolt_url}
    database={outputPort.server.neo4j_database || "neo4j"}
  />
)}
```

---

## Credential Management

Credentials are resolved from environment variables (`NEO4J_PASSWORD`) or the Ontos connections table — never passed as query parameters or stored in code.

**Production path:** Resolve from Databricks UC Secrets at delivery time:
```python
password = ws_client.secrets.get_secret(scope="neo4j", key="password").value
```

---

## ODPS Spec for Derived Data Products

The connector supports generating an ODPS-compatible specification from a live Neo4j instance:

```yaml
dataProduct:
  title: OEM STC Knowledge Graph
  type: consumer_aligned
  outputPorts:
    - name: OEM STC Neo4j Graph
      type: neo4j
      server:
        bolt_url: bolt://host:7687
        neo4j_database: neo4j
      schema:
        nodes:
          - label: MaintenanceEvent
            count: 500
          - label: Part
            count: 104
          - label: Aircraft
            count: 10
        relationships:
          - type: FAULT_OCCURRED_DURING_FLIGHTLEG
            count: 5
      dataFreshness:
        flightleg: "2026-05-28"
        alert: "2026-05-28"
```

---

## How It Relates to the Feeder Engine

| Concern | Handled By |
|---------|-----------|
| Loading data into Neo4j (ETL) | Feeder engine (`neo4j-feeder-engine`) |
| Discovering data products in the catalog | Ontos + this connector |
| Live graph metadata & freshness | This connector (reads from Neo4j) |
| ODPS specification for KG products | Auto-generated from live graph |
| Access provisioning | Future: Ontos delivery service + Neo4j roles |

The feeder engine **builds** the graph. This connector **catalogs** it.

---

## Next Steps

- [ ] Wire `neo4j-graph-panel.tsx` into `data-product-details.tsx`
- [ ] Add Neo4j connection entry in Ontos connections table
- [ ] Resolve credentials from UC Secrets instead of env vars
- [ ] Add "Derived" as a product type option in the UI (currently using "Consumer Aligned")
- [ ] Auto-generate ODPS from live Neo4j on product creation
- [ ] Add lineage view connecting source-aligned products → feeder → Neo4j output

---

## Ontos Production Readiness — Filling the Checklist

When registering a Neo4j derived data product in Ontos, the Production Readiness checklist requires 6 items. Here's how to satisfy each:

### 1. ODPS Metadata Present — Required

**Missing:** name, description, owner_team

| Field | Value |
|-------|-------|
| Title | OEM STC Knowledge Graph |
| Version | 1.0.0 |
| Product Type | Consumer Aligned |
| Status | Draft |
| Domain | Digital Services |
| Owner/Team | Platform Team |
| Description | Derived data product — Neo4j Knowledge Graph serving the chatbot agent. Pulls from source-aligned products (flight operations, maintenance, configuration) and exposes graph nodes, relationships, and properties for fault pattern analysis, fleet correlation, and maintenance recommendations. |
| Tags | neo4j, knowledge-graph, derived |

### 2. At Least One Output Contract — Required

Add an output port:

| Field | Value |
|-------|-------|
| Name | OEM STC Neo4j Graph |
| Version | 1.0.0 |
| Type | neo4j (or "other") |
| Description | Knowledge graph with 16 node types and 4 relationship types. 694 total nodes. Refreshed daily via feeder engine. |
| Asset Identifier | bolt://host:7687/neo4j |
| Server → Host | (Neo4j host) |
| Server → Database | neo4j |
| Server → Additional Properties | `{"bolt_url": "bolt://host:7687", "node_labels": ["MaintenanceEvent","Part","Manufacturer","Aircraft","PartCategory","Complaint","MaintenanceAction","SerializedPart","ComponentRemoval","FlightLeg","Alert","Fault","AHMItem","AHMGroupItem","ShopFinding","ScheduleInterruption"], "relationship_types": ["PART_HAS_SERIALIZED_INSTANCE","FAULT_OCCURRED_DURING_FLIGHTLEG","AHM_ITEM_BELONGS_TO_AHM_GROUP_ITEM","ALERT_BELONGS_TO_AHM_ITEM"]}` |

### 3. Key Fields Mapped to Logical Attributes — Required

Map node labels/properties to logical attributes in Ontos:

| Node Label | Logical Attribute | Description |
|-----------|------------------|-------------|
| FlightLeg | Flight Operation | A single flight segment with departure/arrival |
| Alert | ACMS Alert | Aircraft Condition Monitoring System alert |
| Fault | Fault Event | Fault message from onboard systems |
| MaintenanceAction | Maintenance Record | Work performed on aircraft |
| ComponentRemoval | Part Change | Component removed/installed |
| Aircraft | Aircraft Asset | Physical aircraft (tail number) |
| SerializedPart | Tracked Part | Part with serial number |

### 4. Linked to Business Terms — Optional

Link to ontology/glossary terms if they exist in Ontos:
- ATA Chapter → fault/alert categorization
- MEL → Minimum Equipment List reference
- AOG → Aircraft on Ground (schedule interruption)
- BOM → Bill of Materials (part hierarchy)

### 5. Business Lineage Defined (Upstream) — Required

Add 3 input ports:

| Input Port | Description | Asset Identifier |
|-----------|-------------|-----------------|
| Flight Operations | Source-aligned: flight legs, alerts, faults | catalog.schema (ac_ops) |
| Maintenance (ARMS) | Source-aligned: maintenance actions, component removals, SIs | catalog.schema (raw_arms) |
| Configuration (BOM) | Source-aligned: aircraft/operator-reported BOM | catalog.schema (config) |

### 6. Delivery Channels Defined — Optional

Set up a delivery method pointing to the Neo4j instance:

| Field | Value |
|-------|-------|
| Name | Neo4j Bolt Connection |
| Type | neo4j (custom) |
| Connection | bolt://host:7687 |
| Auth | UC Secrets (scope: neo4j, key: password) |

---

## Requirements Coverage Matrix

The 11 data discovery platform requirements mapped against this connector:

| # | Requirement | Covered? | How |
|---|-------------|----------|-----|
| 1 | Catalog Browsing (search, filter) | Yes | Product registered in Ontos marketplace |
| 2 | Detail View (ODPS, schemas, quality) | Yes | Neo4j Graph Panel shows live metadata |
| 3 | Publishing (ODPS + ODCS, validation) | Yes | ODPS auto-generated from live graph |
| 4 | Access Request | Partial | Product visible, but Neo4j access provisioning not automated |
| 5 | Access Provisioning (UC grants) | No | Neo4j doesn't use UC grants — needs custom Neo4j role management |
| 6 | Usage Monitoring — Producers | Partial | Freshness tracked via Incremental node |
| 7 | Usage Monitoring — Consumers | No | No query logging in this version |
| 8 | Communication (outages) | No | Not in scope — use Ontos comments as workaround |
| 9 | Bug Reporting | No | Not in scope |
| 10 | Contract Sync (drift detection) | Partial | Can compare live metadata vs declared ODPS |
| 11 | Lineage (cross-product) | Yes | Input ports → feeder → Neo4j output mapped |

**Coverage: 5/11 fully, 3/11 partial, 3/11 not covered.**

The combination of this connector + Ontos core covers discovery, detail, publishing, and lineage for Neo4j derived products. Access provisioning and usage monitoring remain gaps that require additional development.

---

## Registering a Neo4j Product in Ontos — Step by Step

### 1. Product Metadata (fixes "ODPS metadata present")

| Field | Value |
|-------|-------|
| Title | OEM STC Knowledge Graph |
| Version | 1.0.0 |
| Product Type | Consumer Aligned |
| Status | Draft |
| Domain | Digital Services |
| Owner/Team | Platform Team |
| Description | Derived data product — Neo4j Knowledge Graph serving the agent chatbot. Pulls from source-aligned products (flight operations, maintenance, configuration) and exposes 694 nodes across 16 labels with 20 relationships for fault pattern analysis, fleet correlation, and maintenance recommendations. |
| Tags | neo4j, knowledge-graph, derived |

### 2. Output Port (fixes "At least one output contract")

Click **Add Output Port** and fill:

| Field | Value |
|-------|-------|
| Name | OEM STC Neo4j Graph |
| Version | 1.0.0 |
| Type/Port Type | neo4j (or "other" if neo4j isn't an option) |
| Description | Knowledge graph with 16 node types and 4 relationship types. 694 total nodes. Refreshed daily via feeder engine. |
| Asset Type | (if dropdown) select closest — maybe "Database" or leave blank |
| Asset Identifier | bolt://neo4j-host:7687/neo4j |

If there's a **Server** section in the output port form:

| Field | Value |
|-------|-------|
| Host | neo4j-host |
| Database | neo4j |
| Additional Properties | `{"bolt_url": "bolt://neo4j-host:7687", "node_labels": ["MaintenanceEvent","Part","Manufacturer","Aircraft","PartCategory","Complaint","MaintenanceAction","SerializedPart","ComponentRemoval","FlightLeg","Alert","Fault","AHMItem","AHMGroupItem","ShopFinding","ScheduleInterruption"], "relationship_types": ["PART_HAS_SERIALIZED_INSTANCE","FAULT_OCCURRED_DURING_FLIGHTLEG","AHM_ITEM_BELONGS_TO_AHM_GROUP_ITEM","ALERT_BELONGS_TO_AHM_ITEM"]}` |

### 3. Input Ports / Upstream Lineage (fixes "Business lineage defined")

Add 3 input ports:

**Input Port 1:**

| Field | Value |
|-------|-------|
| Name | Flight Operations |
| Description | Source-aligned tables: flight legs, alerts, faults |
| Asset Identifier | catalog.schema_flight_ops |

**Input Port 2:**

| Field | Value |
|-------|-------|
| Name | Maintenance (ARMS) |
| Description | Source-aligned tables: maintenance actions, component removals, schedule interruptions |
| Asset Identifier | catalog.schema_maintenance |

**Input Port 3:**

| Field | Value |
|-------|-------|
| Name | Configuration (BOM) |
| Description | Source-aligned tables: aircraft-reported and operator-reported BOM |
| Asset Identifier | catalog.schema_config |

### After filling these in:

You should go from **0/6** to at least **3/6** on the readiness checklist. That demonstrates: "We registered a Neo4j derived data product in Ontos with metadata, an output port pointing to the live KG, and upstream lineage tracing back to source-aligned tables."

---

## Product Type Gap

Ontos currently offers these product types:
- Source
- Source Aligned
- Aggregate
- Consumer Aligned
- Sink

**Missing: "Derived"** — the term defined in the shared glossary for Neo4j Knowledge Graphs that pull from source-aligned products. "Consumer Aligned" is the closest fit today, but adding "Derived" as a type would properly represent the architecture.
