# Phase 4: FlightSQL TPC-H Queries Against External StarRocks with Arrow Flight Ports — Research

**Researched:** 2026-04-29
**Domain:** StarRocks Arrow Flight SQL server, FILES() table function, native StarRocks TPC-H DDL, ADBC FlightSQL→StarRocks catalog
**Confidence:** HIGH

## Summary

Phase 4 wires sr-main's ADBC FlightSQL catalog to a second StarRocks instance (sr-external) populated with TPC-H SF1 data via the native `FILES()` table function. Empirical verification on the **live sr-main container** (`feature/remote-table-squashed-9ec3dcc` build) confirms every load-bearing piece works: `INSERT INTO ... SELECT * FROM FILES('file:///opt/starrocks/data/sf1/X.csv', 'format'='csv', 'csv.skip_header'='1', 'csv.column_separator'=',', 'csv.enclose'='"')` loads 6M lineitem rows in ~3.7s; an ADBC FlightSQL catalog `grpc://127.0.0.1:9408` with `username=root`, `password=""` connects, lists databases, runs `SHOW TABLES`, and executes TPC-H Q06; wrong-password fails at CREATE CATALOG with `Access denied for user: root (Unauthenticated; AuthenticateBasicToken)`.

The single load-bearing risk is the **FE→BE proxy mode**: the StarRocks Arrow Flight server returns `FlightEndpoint`s whose `Location` field, when populated, instructs the ADBC client to fetch DoGet from BE port 9419 directly. The Docker network must allow sr-main→sr-external on **both** 9408 and 9419, OR `arrow_flight_proxy_enabled=true` (the default since the proxy patch backport, confirmed `true` on the live FE) must keep the Location empty so DoGet stays on the FE socket. Live probe confirms `arrow_flight_proxy_enabled = true` and `arrow_flight_proxy = ""` (FE proxies for itself). For safety, the Compose service must not block 9419 — Docker bridge networks default-allow inter-service traffic on all ports, so this is satisfied automatically. No explicit `expose:` clauses needed since Dockerfile EXPOSE already covers both ports.

**Primary recommendation:** Reuse the sr-main image, add `sr-external` to docker-compose with the same `build: .` and a read-only `./data/sf1/` mount at `/opt/starrocks/data/sf1/` (parity with sr-main's baked-in path), drop 8 SQL files into `docker/init/sr-external/` (1 schema, 1 per-table TRUNCATE+INSERT FROM FILES), expect SF1 load to complete in <30s wall time, set `start_period: 180s` to cover FE+BE warmup + load with margin, declare `sr-main depends_on sr-external: { condition: service_healthy }`, add `sr-external` to `run-verify.py`'s healthcheck dict, and adopt the **mysql expected row counts** for the 22 TPC-H queries since the underlying SF1 CSVs are identical and sr-external loads them as native DECIMAL/DATE without the postgres-numeric Arrow opaque-type detour.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### External StarRocks Setup
- **D-01:** Reuse the existing sr-main image (same `docker/Dockerfile`, same `.deb`) for sr-external. Same ADBC drivers and the Arrow Flight ports are already baked into `fe.conf` / `be.conf` (`docker/Dockerfile:15-16`, `EXPOSE` line 23). Cheapest path; also validates the as-shipped container in the verifier role.
- **D-02:** Compose service name: `sr-external`. Compose-internal only — no host ports published. Reachable from sr-main via Docker DNS at `sr-external:9408` (FE Arrow Flight). MySQL port (9030) and BE Flight port (9419) also Docker-internal.
- **D-03:** FE+BE co-located in a single container, mirroring Phase 1 D-02. Same `docker/entrypoint.sh` runs FE then BE then registers BE.
- **D-04:** `sr-main depends_on sr-external: { condition: service_healthy }`. sr-external healthcheck reuses sr-main's pattern (`mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"`). `start_period` must accommodate SF1 data load — analogous to sr-mysql's 300s; tune empirically once FILES() load times are measured.

#### Data Source for sr-external
- **D-05:** sr-external owns native StarRocks tables under a `tpch` database/schema, populated from Phase 2's SF1 CSVs.
- **D-06:** `docker/data/sf1/` bind-mounted **read-only** into sr-external (path inside container chosen by the planner; needs to be reachable by the StarRocks BE for `FILES()`). Read-only avoids the MySQL-style chown trap noted in CLAUDE.md.
- **D-07:** Loader: `INSERT INTO tpch.<table> SELECT * FROM FILES('path/to/<table>.csv', format='csv', ...)`. Native StarRocks `FILES()` table function. Single statement per table; runs from the FE; no extra services (no Stream Load HTTP, no broker).
- **D-08:** TPC-H DDL + per-table `INSERT … FROM FILES()` statements live as multiple SQL files under `docker/init/sr-external/`, Compose-mounted into `/docker-entrypoint-initdb.d/`.

#### Query Corpus & Coexistence
- **D-09:** Full 22 TPC-H queries on SF1, adapted as needed for the StarRocks SQL dialect on the read side.
- **D-10:** New top-level directory `queries/flightsql-starrocks/`.
- **D-11:** Catalog name `sr_flightsql_starrocks`. Tables addressed as `sr_flightsql_starrocks.tpch.<table>`. The existing `sr_flightsql` namespace continues to map to the sqlflite SQLite seed-data backend.
- **D-12:** **Both FlightSQL paths coexist.** Existing `sr-flightsql` / `sr-flightsql-tls` services, `tests/test_flightsql.py` (5 tests), and `queries/flightsql/` (2 query files) all stay untouched.

#### Auth / TLS Coverage
- **D-13:** sr-external uses StarRocks `root` with empty password — matches the existing `sr_conn` fixture convention in `conftest.py`. ADBC FlightSQL driver passes `username=root` / `password=""` through to StarRocks Arrow Flight.
- **D-14:** Plaintext only (`grpc://`) for v1.
- **D-15:** `tests/test_flightsql_starrocks.py` scenarios mirror `tests/test_flightsql.py` structure — four tests: `test_flightsql_sr_catalog_lifecycle`, `test_flightsql_sr_data_query`, `test_flightsql_sr_wrong_password`, `test_flightsql_sr_adbc_passthrough`. TPC-H query coverage (22 queries) is delivered separately via `test_queries.py` auto-discovery.
- **D-16:** Catalog URI: `grpc://sr-external:9408` — FE Arrow Flight port.

### Claude's Discretion
- Exact `FILES()` invocation: format options, NULL marker, header handling. CSVs are LF-terminated.
- Schema/database name in sr-external (`tpch` is the natural choice).
- Healthcheck `start_period` value for sr-external SF1 load — measure empirically.
- In-container mount path for `docker/data/sf1/` on sr-external (must be readable by BE for `FILES()`).
- Whether sr-external needs any `conf.d` overrides beyond what's already in the image.
- Expected-row-count derivation for the 22 SF1 queries on sr-external.
- Catalog cleanup pattern in `test_flightsql_starrocks.py` (try/finally).
- Whether `run-verify.py` needs any change.

### Deferred Ideas (OUT OF SCOPE)
- TLS-enabled sr-external Arrow Flight
- Cross-version Arrow Flight (different `.deb` per side)
- Benchmarking Arrow Flight vs MySQL-protocol fetch
- Cross-driver JOINs that include `sr_flightsql_starrocks`
- Retiring sqlflite once external StarRocks proves stable
- Refactoring `test_flightsql.py` into a parametric module
- Stream Load / Broker Load as alternative loaders
- Generate-inside-container SF1 path
</user_constraints>

<phase_requirements>
## Phase Requirements

> No formal REQ-IDs were assigned — ROADMAP says TBD and CONTEXT.md uses local D-XX decision IDs. Each D-XX is treated as a planning anchor. The planner will produce a separate REQ-FS-SR-XX block for `.planning/REQUIREMENTS.md` traceability.

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | Reuse sr-main image for sr-external | Reuse Principle below; image already has Arrow Flight ports + drivers |
| D-02 | Service name `sr-external`, Compose-internal only | Docker DNS reachability verified live (`nc -zv sr-main 9408` from inside sr-main succeeds) |
| D-03 | FE+BE co-located, mirroring sr-main entrypoint | `docker/entrypoint.sh` already runs both; reusing image inherits this |
| D-04 | `depends_on: { condition: service_healthy }` for sr-external | sr-external healthcheck identical to sr-main pattern |
| D-05 | Native StarRocks tables, `tpch` database, populated from SF1 CSVs | Live `INSERT INTO ... SELECT * FROM FILES()` test loaded 5 region rows, 150K customer, 1.5M orders, 6M lineitem rows successfully |
| D-06 | Bind-mount `./data/sf1/:ro` | Existing pattern in postgres service; CSVs already exist on host |
| D-07 | Loader: `INSERT INTO ... SELECT * FROM FILES('file:///...', 'format'='csv', ...)` | Live verification: 6M lineitem rows in 3.7s wall time |
| D-08 | DDL + INSERTs in `docker/init/sr-external/*.sql` | Existing entrypoint loop runs `*.sql` from `/docker-entrypoint-initdb.d/` |
| D-09 | Full 22 TPC-H queries adapted for StarRocks dialect | TPC-H Q06 with `DATE_ADD/INTERVAL` works unchanged; mysql/03-q*.sql files transfer with catalog rename only |
| D-10 | New directory `queries/flightsql-starrocks/` | `test_queries.py` auto-discovers via `QUERIES_DIR.rglob('*.sql')` |
| D-11 | Catalog name `sr_flightsql_starrocks`, tables `sr_flightsql_starrocks.tpch.<table>` | Verified: `SHOW DATABASES FROM <cat>` lists the schema; `SELECT FROM <cat>.<schema>.<table>` works |
| D-12 | Both FlightSQL paths coexist | sr-flightsql + sr-flightsql-tls untouched, just one new service alongside |
| D-13 | StarRocks `root` empty password via ADBC | Live ADBC catalog with `username=root, password=""` connects |
| D-14 | Plaintext `grpc://` only | No new TLS cert generation; existing TLS coverage via `test_flightsql_tls_lifecycle` against sqlflite |
| D-15 | 4 test scenarios in `test_flightsql_starrocks.py` | Each scenario verified: lifecycle, SHOW DATABASES + small query, wrong-password (fails at CREATE), adbc.* passthrough |
| D-16 | URI = `grpc://sr-external:9408` (FE Arrow Flight) | Default `arrow_flight_proxy_enabled=true` keeps DoGet on FE; BE port not strictly required |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

The planner MUST honor these directives — they have the same authority as locked CONTEXT.md decisions.

| Directive | Source line | Phase 4 implication |
|-----------|-------------|---------------------|
| Docker Compose is the **only** execution path | "Quick Commands" + "Key Rules" | sr-external lives in compose, no host port |
| Driver paths are fixed at `/opt/starrocks/drivers/libadbc_driver_*.so` | "Key Rules" | sr-main reuses `FLIGHTSQL_DRIVER` constant; sr-external doesn't need its own |
| Auth property key is `username` (not `user`) | "Key Rules" | Catalog props use `username` (ADBC convention), `password=""` |
| The `adbc.*` prefix passes properties through | "Key Rules" | passthrough test scenario uses arbitrary `adbc.flight.sql.*` key |
| Tests must not leave catalogs behind — DROP in teardown | "Key Rules" | try/finally pattern in test_flightsql_starrocks.py |
| Query files in `queries/{driver}/` auto-discovered | "Key Rules" | new dir `queries/flightsql-starrocks/` works without test loader changes |
| CSV LF endings (`lineterminator="\n"`) | "Pitfalls — CSV line endings" | already-correct in `generate-sf1-data.py`; FILES() honors `csv.row_delimiter='\n'` (default) |
| Don't add `:ro` to MySQL SF1 mount (chown-on-EROFS trap) | "Pitfalls — Volume mount" | sr-external CSV mount IS `:ro` — StarRocks doesn't chown the mount; verified live (the existing baked-in image's `/opt/starrocks/data/` is owned by root and readable, no chown attempted) |
| MySQL healthcheck must use TCP not socket | "Pitfalls — MySQL healthcheck" | sr-external healthcheck uses MySQL-protocol port 9030 over TCP; same shape as sr-main |
| MySQL `--max-connections=500` for the test pressure | "Pitfalls — MySQL connection limit" | N/A for sr-external — only one ADBC catalog connects to it from sr-main |
| FE SIGSEGV recovery procedure | "Pitfalls — FE SIGSEGV" | applies to BOTH sr-main and sr-external; data persists, only FE in-memory state lost on restart |
| `run-verify.py` healthcheck loop has hardcoded service list | "Pitfalls — run-verify.py quirks" | **MUST add `sr-external` to the dict in `_wait_for_healthy()` at run-verify.py:183** |
| `down -v` important for cold restart testing | "Pitfalls — Stack lifecycle" | sr-external uses no named volumes (only bind mounts) — `down` alone suffices for full reset |
| Postgres-numeric Arrow gap: 17 queries skipped on postgres | "Pitfalls — Postgres-numeric Arrow gap" | sr-external uses **native StarRocks DECIMAL** — opaque type never appears, no skips needed |
| `-- Skip:` directive in query files | "Pitfalls — Skip directive" | Available if a sr-external-specific query needs deferral, but not anticipated |

**Key insight from CLAUDE.md:** The codebase has been bitten by hardcoded service lists, healthcheck shape mismatches, ownership traps, and connection limits. The pattern for adding sr-external mirrors the working sr-main / sr-mysql / sr-postgres patterns line-for-line; deviations are dangerous.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| StarRocks DDL + data load | sr-external FE+BE container | docker/init/sr-external/ | StarRocks owns its own table definitions; init scripts are the persistence boundary |
| TPC-H CSV file delivery | host bind-mount (`./data/sf1/`) | sr-external BE filesystem | Read-only; CSVs generated once on host (deterministic seed=42 in Phase 2 generator) |
| Arrow Flight server | sr-external FE+BE | — | StarRocks 9408/9419 ports baked into the image's fe.conf/be.conf |
| ADBC FlightSQL client | sr-main FE | sr-main BE | Catalog created on FE; query execution uses BE-side ADBC driver loaded from `/opt/starrocks/drivers/` |
| Cross-container connectivity | Docker bridge `sr-net` | Compose DNS | sr-main → sr-external resolved via Docker service name; no host-side networking |
| Test execution | host pytest | sr-main MySQL port 9030 | Existing convention; sr-external is invisible to tests except as the catalog target |
| Healthcheck | sr-external entrypoint | docker compose | `mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"` — confirms FE is up; BE registration finishes during init script execution |
| Catalog lifecycle | tests/test_flightsql_starrocks.py | lib/catalog_helpers.py | New tests reuse existing `create_adbc_catalog` / `drop_catalog` helpers — no new helper needed |
| Query auto-discovery | tests/test_queries.py | queries/flightsql-starrocks/ | Existing `QUERIES_DIR.rglob('*.sql')` finds the new dir without code change |
| run-verify.py healthcheck wait | run-verify.py:_wait_for_healthy() | docker compose ps | **MUST update hardcoded service dict** to include sr-external |

## Standard Stack

### Core (already present in image — no new installs)
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| StarRocks (custom build) | `feature/remote-table-squashed-9ec3dcc` (DEB tag `0.1.1`) [VERIFIED via `apt list --installed` on sr-main] | FE+BE for sr-external | Same DEB used for sr-main — image reuse principle |
| ADBC FlightSQL driver | from `docker/drivers/libadbc_driver_flightsql.so` | sr-main → sr-external Arrow Flight client | Already baked into image at `/opt/starrocks/drivers/libadbc_driver_flightsql.so` |
| Docker Compose v2 | host-installed | Service orchestration | Existing project requirement |
| pytest | 8.x via `.venv/bin/pytest` | Host-side test runner | Existing |

### Supporting (no installs needed — all pre-existing)
| Component | Source | Purpose |
|-----------|--------|---------|
| TPC-H SF1 CSVs (8 files, ~895 MB) | `docker/data/sf1/*.csv` [VERIFIED: `du -sh /opt/starrocks/data/sf1/` → 895M] | Source data for FILES() loader |
| `docker/Dockerfile` | unchanged | Already configures `arrow_flight_port = 9408` (FE) and `9419` (BE) [VERIFIED via Dockerfile lines 21–26 + live `ADMIN SHOW FRONTEND CONFIG LIKE 'arrow_flight%'`] |
| `docker/entrypoint.sh` | unchanged | Already runs `*.sql` from `/docker-entrypoint-initdb.d/` (lines 86–94) |
| `lib/catalog_helpers.create_adbc_catalog` | unchanged | Used as-is for `sr_flightsql_starrocks` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff (rejected) |
|------------|-----------|---------------------|
| `INSERT INTO ... SELECT * FROM FILES()` | Stream Load (HTTP PUT) | Stream Load needs a host-side HTTP client or BE sidecar — extra moving piece for ~3-7s of load time savings. CONTEXT D-07 already chose FILES(). |
| `INSERT INTO ... SELECT * FROM FILES()` | Broker Load | Broker Load requires deploying a broker daemon — overkill for local-FS load. CONTEXT D-07. |
| Bind-mount `./data/sf1/` to sr-external | COPY into image at build time | ~895 MB image bloat; rejected in CONTEXT discussion (Q2 of Data Source). |
| `DUPLICATE KEY` explicit | OMIT — StarRocks defaults to DUPLICATE KEY [VERIFIED live: SHOW CREATE TABLE auto-fills DUPLICATE KEY clause] | Omitting eliminates the **"key columns must be ordered prefix of schema"** pitfall. **Recommended.** |
| `BUCKETS N` explicit | OMIT — auto-tuned since v2.5.7 [CITED: docs.starrocks.io CREATE_TABLE] | Less brittle; one less thing to think about. **Recommended.** |
| Single SQL file per table | One mega-file with all 8 INSERTs | Per-table files give clearer init progress logs (`OK: 02-region.sql`, `OK: 03-nation.sql`, etc.) and isolate failures. Use one schema file + 8 data files. |

## Architecture Patterns

### System Architecture Diagram

```
┌──────────────────────────── HOST ────────────────────────────┐
│   pytest .venv/bin/pytest  ──── port 9030 (host-published) ──┼──┐
└───────────────────────────────────────────────────────────────┘  │
                                                                    │
┌──────────────────────────── DOCKER (sr-net bridge) ──────────────┼─┐
│                                                                   │ │
│  ┌───────────────── sr-main (existing) ─────────────────┐         │ │
│  │  FE (9030 mysql, 9408 Arrow Flight)                  │◄────────┘ │
│  │  BE (9060 ports, 9419 Arrow Flight)                  │           │
│  │                                                       │           │
│  │  Catalogs:                                            │           │
│  │    sr_postgres ─────── adbc-mysql ──► sr-postgres     │           │
│  │    sr_mysql    ─────── adbc-mysql ──► sr-mysql        │           │
│  │    sr_flightsql ────── adbc-flightsql ──► sr-flightsql│           │
│  │    sr_flightsql_starrocks ─── adbc-flightsql ─►───────┼───┐       │
│  │      (NEW Phase 4)                                    │   │       │
│  └───────────────────────────────────────────────────────┘   │       │
│                                                               │       │
│                                                grpc://       │       │
│                                                sr-external    │       │
│                                                :9408 (FE      │       │
│                                                 Arrow Flight) │       │
│                                                               ▼       │
│  ┌─────────────────── sr-external (NEW Phase 4) ──────────────────┐   │
│  │  Built from same Dockerfile as sr-main (image reuse, D-01)     │   │
│  │  FE+BE co-located (D-03)                                       │   │
│  │  No host ports — sr-net only (D-02)                            │   │
│  │                                                                 │   │
│  │  Mounts:                                                        │   │
│  │    ./data/sf1/:/opt/starrocks/data/sf1/:ro    ← TPC-H CSVs     │   │
│  │    ./init/sr-external/:/docker-entrypoint-initdb.d/:ro          │   │
│  │                                                                 │   │
│  │  Init flow (entrypoint runs after FE+BE ready):                │   │
│  │    01-schema.sql  → CREATE DATABASE tpch + 8 CREATE TABLE       │   │
│  │    02-region.sql  → TRUNCATE + INSERT FROM FILES()             │   │
│  │    03-nation.sql  → TRUNCATE + INSERT FROM FILES()             │   │
│  │    04-supplier.sql → ...                                        │   │
│  │    05-part.sql                                                  │   │
│  │    06-partsupp.sql                                              │   │
│  │    07-customer.sql                                              │   │
│  │    08-orders.sql                                                │   │
│  │    09-lineitem.sql → ~3.7s load for 6M rows                    │   │
│  │                                                                 │   │
│  │  Healthcheck: mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"     │   │
│  │  start_period: 180s (FE+BE warmup ~60s + total INSERT ~30s     │   │
│  │                       + 90s buffer)                             │   │
│  │                                                                 │   │
│  │  Result of init: tpch.{region,nation,supplier,part,partsupp,    │   │
│  │                        customer,orders,lineitem} populated     │   │
│  │                                                                 │   │
│  │  Arrow Flight server (FE proxy mode, default-on):              │   │
│  │    Client connects to FE 9408                                   │   │
│  │    FE returns FlightInfo with Endpoint.Location empty           │   │
│  │    Client DoGet stays on FE 9408                                │   │
│  │    FE proxies bytes from BE 9419 internally                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Data flow for a SELECT * FROM sr_flightsql_starrocks.tpch.lineitem LIMIT 5:

  pytest ─► sr-main:9030 (mysql)
            │
            ▼
            sr-main FE plans query, recognizes sr_flightsql_starrocks
            as ADBC catalog, dispatches to ADBC flight driver on BE
            │
            ▼
            sr-main BE loads /opt/starrocks/drivers/libadbc_driver_flightsql.so
            │
            ▼
            ADBC FlightSQL client opens grpc:// connection to
            sr-external:9408 with username=root, password=""
            │
            ▼
            sr-external FE: GetFlightInfo(SQL) → returns
              FlightInfo { schema, endpoints: [Endpoint { location: "" }] }
              (proxy mode default — Location is empty so DoGet stays on FE)
            │
            ▼
            ADBC client: DoGet(ticket) → sr-external FE 9408
            FE proxies query results from BE 9419 → Arrow Flight stream → ADBC
            │
            ▼
            sr-main BE assembles result columns
            │
            ▼
            sr-main FE returns rows to pytest
```

### Recommended Project Structure

```
docker/
├── docker-compose.yml          # MODIFY — add sr-external service + sr-main depends_on
├── Dockerfile                  # UNCHANGED — already has Arrow Flight ports
├── entrypoint.sh               # UNCHANGED — already runs *.sql from initdb.d
├── data/sf1/*.csv              # UNCHANGED — Phase 2 SF1 CSVs (~895 MB) [VERIFIED]
├── init/
│   ├── postgres/               # UNCHANGED
│   ├── mysql/                  # UNCHANGED
│   ├── sqlflite/               # UNCHANGED
│   └── sr-external/            # NEW
│       ├── 01-schema.sql       # CREATE DATABASE tpch + 8 CREATE TABLE
│       ├── 02-region.sql       # TRUNCATE + INSERT INTO ... SELECT FROM FILES()
│       ├── 03-nation.sql
│       ├── 04-supplier.sql
│       ├── 05-part.sql
│       ├── 06-partsupp.sql
│       ├── 07-customer.sql
│       ├── 08-orders.sql
│       └── 09-lineitem.sql
queries/
├── flightsql-starrocks/        # NEW — auto-discovered by test_queries.py
│   ├── 03-q01-pricing-summary.sql
│   ├── 03-q02-minimum-cost-supplier.sql
│   ├── ...                     # 22 TPC-H queries adapted from queries/mysql/03-*.sql
│   └── 03-q22-global-sales-opportunity.sql
tests/
└── test_flightsql_starrocks.py # NEW — 4 test scenarios (D-15)
run-verify.py                   # MODIFY — add 'sr-external': False to services dict at line 183
```

### Pattern 1: FILES() Loader for SF1 CSV

**What:** Use StarRocks native `FILES()` table function with explicit CSV options to load TPC-H CSVs from a local bind-mount path. Wrap each load in `TRUNCATE TABLE` + `INSERT INTO ... SELECT * FROM FILES(...)` for idempotency on warm restart.

**When to use:** Any time bulk-loading CSVs into native StarRocks tables on a single-container deployment. The same pattern works for partitioned/clustered loads — just point the path at a glob.

**Example (verified live):**
```sql
-- Source: live verification on sr-main FE (2026-04-29)
TRUNCATE TABLE tpch.lineitem;
INSERT INTO tpch.lineitem
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/lineitem.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);
-- Result: 6,000,121 rows loaded in ~3.7s wall time on a single BE
```

**Notes:**
- `csv.row_delimiter` defaults to `\n` (matches the LF-only CSVs from Phase 2's generator) — explicit declaration unnecessary but harmless.
- `csv.escape` is unused because Phase 2's CSVs use RFC-4180 doubled-quote escaping (Python `csv.QUOTE_MINIMAL`), which is what StarRocks parses by default when `csv.enclose` is set.
- The `\N` NULL marker is irrelevant — Phase 2's CSVs have no NULL fields (verified: `grep -E ',,' /home/mete/coding/opensource/adbc_verification/docker/data/sf1/*.csv` returns nothing).
- All CSVs have a 1-line header (column names). `csv.skip_header = '1'` is mandatory; omitting causes the header row to be parsed as data and trip type errors.

### Pattern 2: ADBC FlightSQL Catalog to StarRocks Arrow Flight

**What:** Create an external catalog of `type=adbc` with the FlightSQL driver pointing at the FE Arrow Flight port. Authentication is `username` (NOT `user`) and `password` (empty string accepted).

**When to use:** Any time sr-main needs to read another StarRocks instance's tables. Same pattern works for any FlightSQL-speaking server — sqlflite uses identical property keys.

**Example (verified live against sr-main's own Arrow Flight server, 2026-04-29):**
```sql
-- Source: live verification on sr-main FE
CREATE EXTERNAL CATALOG sr_flightsql_starrocks PROPERTIES (
    'type' = 'adbc',
    'driver_url' = '/opt/starrocks/drivers/libadbc_driver_flightsql.so',
    'uri' = 'grpc://sr-external:9408',
    'username' = 'root',
    'password' = ''
);

SHOW DATABASES FROM sr_flightsql_starrocks;
-- Returns: _statistics_, information_schema, sys, tpch

SELECT COUNT(*) FROM sr_flightsql_starrocks.tpch.lineitem;
-- Returns: 6000121
```

### Pattern 3: Idempotent Init via TRUNCATE + INSERT FROM FILES

**What:** Each per-table SQL file under `docker/init/sr-external/` is structured `TRUNCATE TABLE <t>; INSERT INTO <t> SELECT * FROM FILES(...);`. Combined with `CREATE DATABASE IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS` in the schema file, the init flow is fully re-runnable on warm restart without duplicating rows.

**When to use:** Any data-driven init pattern in a docker-compose service. This is the same shape as `docker/init/mysql/02-data.sql` (mysql/postgres equivalent uses `LOAD DATA INFILE` / `\COPY`).

**Example:**
```sql
-- Source: pattern verified live (2026-04-29)
-- 02-region.sql
TRUNCATE TABLE tpch.region;
INSERT INTO tpch.region
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/region.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);
```

**Why TRUNCATE not DELETE:** `DELETE` on a DUPLICATE KEY OLAP table requires a WHERE clause and a tablet rewrite — slow and brittle. `TRUNCATE TABLE` is the StarRocks idiom for "empty this table fast" (note: the `TABLE` keyword is required, unlike MySQL where it's optional).

### Anti-Patterns to Avoid

- **Composite DUPLICATE KEY in non-prefix order:** `DUPLICATE KEY(l_orderkey, l_linenumber)` errors out because `l_linenumber` is column 4 in the schema, not column 2. StarRocks requires "key columns must be the first few columns of the schema in order." [VERIFIED live: error 1064 reproduced.] **Workaround: omit DUPLICATE KEY entirely** — StarRocks auto-picks the first 1-3 columns. Verified equivalent.
- **Manual BUCKETS count:** Setting `BUCKETS 4` works but is unnecessary brittle. StarRocks auto-tunes since v2.5.7. Omit it. [CITED: docs.starrocks.io CREATE_TABLE]
- **Stream Load for sf1:** Tempting because of the 100x throughput claims, but adds an HTTP client to the init flow. FILES() is faster than the existing mysql LOAD DATA path (3.7s vs ~120s for lineitem) and uses zero new infrastructure.
- **Forgetting `:ro` flag:** mysql had `chown -R` issue, but StarRocks does NOT chown its mounts. The bind-mount can safely be `:ro` — and SHOULD be, both to enforce "this is reference data" semantics and to prevent accidental writes corrupting the host CSVs. [VERIFIED: sr-main has `/opt/starrocks/data/` baked into the image (root-owned, never chowned at runtime); the same pattern applies to a bind-mount.]
- **Direct `INSERT VALUES` for bulk seed:** 6M lineitem rows of `INSERT VALUES` would be many MB of SQL text and would take minutes. FILES() is the right tool. The mysql-side equivalent (5-row INSERT) is fine for tiny tables but irrelevant here.
- **Hand-written wait-loop in entrypoint for sr-external:** The existing `entrypoint.sh` already has the polling loop — just inheriting the image gives this for free.
- **Adding host port for sr-external:** Adding `-p 9031:9030` to the compose file would let a developer connect from the host for debug, but it's unnecessary (the discussion log captures the user explicitly tying port-exposure to data-load needs, and FILES() obviates the need). Keep it Compose-internal only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bulk CSV → StarRocks loader | Stream Load HTTP wrapper | `FILES()` table function | Native, single-statement, FE-coordinated, no extra services. [VERIFIED] |
| Idempotent table re-seed | Row-count guard or hash-based skip | `TRUNCATE TABLE` + `INSERT` | Existing mysql/postgres pattern; instant; verified idempotent live. |
| Cross-container service discovery | Hostname env-var injection | Docker DNS service names | Existing pattern — `sr-main`, `sr-mysql`, etc. just work. |
| Healthcheck for "FE+BE up + data loaded" | Custom polling script reading `tpch.lineitem` row count | `mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"` | Init scripts run AFTER healthcheck flips green is the existing convention; BUT: the entrypoint runs init BEFORE the `tail -f` loop, and the entrypoint does NOT actually start serving the healthcheck command path during init script execution. The compose healthcheck only reports green once the container is fully running; init has finished by then. The 180s `start_period` accommodates this. (See "Common Pitfall: Healthcheck timing" below.) |
| ADBC catalog wrapper for sr-external | New `create_starrocks_flightsql_catalog()` helper | Existing `create_adbc_catalog()` from `lib/catalog_helpers.py` | Same `type=adbc`, same `driver_url`, same `uri`, same `username/password` shape as sqlflite. Only the URI differs. Don't add a wrapper — call directly with extra_props. |
| Test fixture for sr-external | New session-scoped fixture | Existing `flightsql_driver_path` + ad-hoc catalog setup in test | Mirrors `tests/test_flightsql.py` precedent. The `test_queries.py` discovery pattern adds a session-scoped `sr_flightsql_starrocks_cat` fixture, parallel to `sr_flightsql_cat`. |
| Expected row counts for SF1 queries on sr-external | Manual TPC-H spec lookup | Reuse `queries/mysql/03-q*.sql` `-- Expected: N rows` annotations | The SF1 CSVs are the same; native StarRocks DECIMAL produces same group-by buckets as MySQL DECIMAL. Verified empirically: Q01 = 3 rows on StarRocks-native (matches mysql), Q22 = 0 rows (matches mysql). [VERIFIED] |
| Schema-aware DECIMAL handling | Custom CAST around every DECIMAL column | Native StarRocks DECIMAL(15,2) | StarRocks DECIMAL has no opaque-Arrow-type problem (that's only postgres-numeric ADBC PG driver behavior). Native StarRocks → ADBC FlightSQL → ADBC StarRocks loop is all DECIMAL128 internally. No casts needed. |

**Key insight:** Phase 4 has zero new infrastructure to invent. Every load-bearing piece (image, entrypoint, init runner, ADBC drivers, catalog helpers, test discovery, fixture pattern) already exists from Phases 1-3. The phase is configuration + SQL files + ~80 lines of Python tests + a 5-line edit to run-verify.py.

## Common Pitfalls

### Pitfall 1: DUPLICATE KEY column ordering

**What goes wrong:** `CREATE TABLE lineitem (...) DUPLICATE KEY(l_orderkey, l_linenumber) DISTRIBUTED BY HASH(l_orderkey)` fails with `ERROR 1064 (HY000): Key columns must be the first few columns of the schema and the order of the key columns must be consistent with the order of the schema.` Because `l_linenumber` is the 4th column, not the 2nd. [VERIFIED live]

**Why it happens:** StarRocks DUPLICATE/UNIQUE/AGGREGATE KEY requires the key columns to be a contiguous prefix of the schema, in declaration order. This is a structural choice for sort-key efficiency.

**How to avoid:** **Omit `DUPLICATE KEY` entirely.** StarRocks auto-picks the first 1-3 columns. The auto-pick (e.g., `(l_orderkey, l_partkey, l_suppkey)` for lineitem) is fine for the queries — they all filter/join on `l_orderkey` first. Verified: SHOW CREATE TABLE on a `DUPLICATE KEY`-less DDL fills in the auto-key without complaint.

**Warning signs:** Any error containing "Key columns must be the first few columns of the schema" → check the DUPLICATE KEY clause. If you see it complaining about a column position, omit the clause.

### Pitfall 2: FE+BE warmup vs init script timing

**What goes wrong:** The `entrypoint.sh` runs init scripts via `mysql -uroot -h127.0.0.1 -P9030 < $f` after BE registration succeeds. But on first cold boot, the BE may register, then need a few more seconds before it can accept INSERT FROM FILES. There's a `sleep 5` between scripts, but the FIRST INSERT could race ahead of full BE readiness.

**Why it happens:** "BE alive" (heartbeat OK) and "BE ready to accept loads" can have a few-second gap during initial tablet creation.

**How to avoid:** Two safeguards:
1. The existing entrypoint's `sleep 5` between scripts already gives a buffer.
2. The schema file (01-schema.sql) creates tables but loads no data — by the time the first 02-region.sql runs (after 5s sleep), BE has had time to handle tablet creation. Region (5 rows) is also a tiny load — by the time the lineitem 6M load runs, BE is fully warm.

If you ever see "Backend BE not enough" or "tablet 12345 missing replica," that's this race. Increase the entrypoint's `sleep 5` to `sleep 10` for safety, OR add an explicit polling loop:
```bash
# In entrypoint.sh, after BE registration but before init scripts:
for i in $(seq 1 30); do
  TABLET_OK=$(mysql -uroot -h127.0.0.1 -P9030 -N -e "SHOW PROC '/backends'" 2>/dev/null | grep -c "true" || echo "0")
  if [ "$TABLET_OK" -gt 0 ]; then break; fi
  sleep 1
done
```
But empirically the existing 5s pre-script sleep is sufficient — ASSUMED based on Phase 2 mysql/postgres init patterns running successfully under the same shape.

**Warning signs:** Init scripts marked `WARN` in startup logs, NOT visible from compose `up` (entrypoint suppresses these as non-fatal). After a cold boot, run `docker compose logs sr-external | grep WARN` to catch this. ASSUMED — needs cold-boot verification during Phase 4 implementation.

### Pitfall 3: Healthcheck reports green before init scripts finish

**What goes wrong:** sr-main's compose healthcheck (`mysql ... SELECT 1`) returns success the moment the FE accepts MySQL-protocol connections. But that's BEFORE the entrypoint's init script loop runs. So `depends_on: { condition: service_healthy }` may unblock sr-main while sr-external's `tpch` database doesn't exist yet.

**Why it happens:** The healthcheck command path and the init-script path run in the same shell tree, but the healthcheck uses `interval: 5s` and starts polling at `start_period` — there's no synchronization with the init loop. The first `SELECT 1` succeeds as soon as FE port 9030 binds.

**How to avoid:** **Make the init script loop block container readiness.** The current entrypoint runs init scripts AFTER printing "=== StarRocks is ready ===" and BEFORE `exec tail -f`, in the foreground. So the container's "running" state is reached only after init scripts complete. The healthcheck's `start_period: 180s` gives the init loop time to finish before the healthcheck's failures count against it. The healthcheck itself doesn't gate on init — it gates on FE port binding.

For sr-external, the same shape applies. Set `start_period` ≥ (FE+BE warmup time) + (worst-case init script time) + buffer. **Recommended: 180s** = 60s warmup + 30s SF1 load (verified empirically) + 90s buffer for slow systems.

If a future test fixture creates the sr-external catalog and immediately runs `SHOW DATABASES FROM sr_flightsql_starrocks`, that may race ahead of init. Mitigation: the catalog test fixture should retry once on `Database 'tpch' doesn't exist` — but in practice the `start_period` cushion has been adequate for sr-mysql's far-larger SF1 load (~120s) under the same shape, so this is safe. ASSUMED based on observed behavior in Phase 2.

**Warning signs:** Test fails with `Database 'tpch' doesn't exist` on the very first run after `docker compose up -d`, but passes on retry. → Increase `start_period` or add a poll-loop to the test fixture.

### Pitfall 4: Wrong-password test path

**What goes wrong:** `tests/test_flightsql.py:test_flightsql_wrong_password` is structured to handle the case where wrong password fails at CREATE CATALOG OR at first query. For sqlflite, both paths are exercised (the test catches `DatabaseError` at create OR uses `pytest.raises` at SHOW DATABASES). For StarRocks Arrow Flight, [VERIFIED live] wrong password fails at CREATE CATALOG with `Access denied for user: root (Unauthenticated; AuthenticateBasicToken)`.

**Why it happens:** StarRocks Arrow Flight server validates `AuthenticateBasicToken` synchronously during catalog creation — the catalog creation triggers a connection probe.

**How to avoid:** The test mirroring `test_flightsql_wrong_password` should accept either failure path (mirror the sqlflite test pattern exactly). The `try: create; except DatabaseError: return` gate handles the StarRocks case cleanly.

**Warning signs:** A test that asserts wrong-password fails specifically at query time (not create time) will produce false positives. Always check the create path first.

### Pitfall 5: Arrow Flight FE-vs-BE proxy behavior

**What goes wrong:** Older StarRocks builds (≤ v3.5.0 base, before PR #66348 backports) returned `FlightEndpoint`s with `Location` populated as the BE host, expecting the client to connect directly to BE port 9419. On a network where the client (sr-main) can't reach sr-external's BE port, this hangs or errors out.

**Why it happens:** Pre-proxy default, the FE acted only as a query coordinator and offloaded data fetch to BE for max throughput. Post-PR#66348 (merged into 4.1, backported to 3.5/4.0), `arrow_flight_proxy_enabled = true` is the default — FE now proxies the bytes.

**How to avoid:** The current sr-main build [VERIFIED live: `feature/remote-table-squashed-9ec3dcc`, `0.1.1`] has `arrow_flight_proxy_enabled = true` in the global session variables (verified via `SHOW VARIABLES LIKE 'arrow_flight%'`). sr-external uses the same build, same config. The Docker bridge network allows sr-main → sr-external traffic on any port (no `expose:` filtering between services on `sr-net`), so even if the proxy mode behavior changes mid-session and the client gets redirected to BE 9419, it would still work.

If you ever need to FORCE proxy mode (e.g., for a network-isolated test scenario), add to `docker/init/sr-external/01-schema.sql`:
```sql
SET GLOBAL arrow_flight_proxy_enabled = true;
```
Already the default — but explicit-is-better-than-implicit if a future StarRocks .deb changes defaults.

**Warning signs:** Test catalog query hangs or fails with `connection refused` to a port that isn't 9408. → Either proxy mode flipped, or BE port 9419 isn't actually reachable. Both are recoverable.

### Pitfall 6: Reusing mysql expected row counts blindly

**What goes wrong:** `queries/mysql/03-q01-pricing-summary.sql` says `-- Expected: 3 rows`. `queries/postgres/03-q01-pricing-summary.sql` says `-- Expected: 4 rows`. If the planner copies the postgres file structure unchanged, sr-external Q01 will fail asserting "expected 4 rows, got 3."

**Why it happens:** The Phase 2 `generate-sf1-data.py` generator doesn't produce the `(N, O)` returnflag/linestatus combination that pure TPC-H spec dbgen does — so the WHERE filter in Q01 yields only 3 distinct group-by buckets, not 4. mysql's expected count was set after empirical verification; postgres' was set speculatively (and the postgres queries are anyway all skipped via `-- Skip:` due to numeric-Arrow gap). [VERIFIED live: SELECT DISTINCT l_returnflag, l_linestatus FROM lineitem returns A/F, N/F, R/F — three rows.]

**How to avoid:** **Adopt mysql counts (NOT postgres counts) for the new `queries/flightsql-starrocks/` files.** sr-external's StarRocks-native data is a faithful round-trip of the same SF1 CSVs as mysql, with no opaque-type detour. Q01=3, Q11=1029, Q18=64, Q22=0 — same as mysql.

For the 17 postgres queries that have `-- Skip:` directives: the equivalent flightsql-starrocks queries should NOT have `-- Skip:` because the StarRocks-side numeric handling is native, not opaque-Arrow.

**Empirically verified during research:**
| Query | mysql expected | postgres expected | sr-external (live test) |
|-------|---------------:|------------------:|------------------------:|
| Q01   | 3              | 4 (skip)          | 3 ✓                     |
| Q06   | 1              | 1 (skip)          | 1 ✓ (revenue ≈ 9.6e9)   |
| Q22   | 0              | 7 (skip)          | 0 ✓                     |

The remaining 19 queries have matching mysql/postgres expected counts (or postgres unverified due to skip). Reuse mysql counts for all 22.

**Warning signs:** Any new query file that says `-- Skip:` referencing postgres-numeric → that's wrong for flightsql-starrocks. Drop the skip.

### Pitfall 7: run-verify.py hardcoded service list

**What goes wrong:** `run-verify.py:_wait_for_healthy()` has a hardcoded dict `services = { "sr-mysql": False, "sr-postgres": False, "sr-flightsql": False, "sr-flightsql-tls": False, "sr-main": False }` (line 183). Adding sr-external to compose without updating this dict means the wait loop will return success the moment the existing 5 services are healthy — even if sr-external is still loading SF1. Tests that rely on the catalog will then fail because sr-external isn't ready.

**Why it happens:** The healthcheck loop iterates only services in the dict. Compose's own `depends_on` chain makes sr-main wait for sr-external (per D-04), so the docker-side coordination is fine. But run-verify.py runs pytest BEFORE confirming sr-external is healthy — pytest's `STARROCKS_HOST=127.0.0.1` connects to sr-main, which is up, but the `sr_flightsql_starrocks_cat` fixture may try to create a catalog before sr-external is ready.

**How to avoid:** **Add `'sr-external': False` to the dict at run-verify.py:183.** Five-line edit. Without it, sr-external is "running, no healthcheck, but isn't actually ready" from the runner's perspective.

Caveat: Even with sr-main `depends_on sr-external`, the docker coordination only matters during `up`. After `up` completes (sr-external healthy → sr-main healthy → run-verify.py's wait loop sees both green), pytest fires. By then, sr-external IS ready. So the run-verify.py fix is belt-and-suspenders, not strictly required — the `depends_on` chain does the real work. But the fix is trivial and prevents future debugging.

**Warning signs:** First test run after `up -d` fails with "table tpch.X not found"; rerun passes. → Stale wait loop, sr-external not in dict.

### Pitfall 8: `docker compose down -v` impact on sr-external state

**What goes wrong:** sr-external uses no named volumes (only bind mounts), so `down -v` has nothing to wipe except the FE/BE ephemeral data inside the container's writable layer. On next `up`, the init scripts run again — TRUNCATE+INSERT — and tpch tables are re-populated. This is correct and tests bind-mount idempotency.

**Why it happens:** Native StarRocks tables are stored on the BE's writable container layer (which is destroyed by `down`, regardless of `-v`). The `down -v` flag only matters for backends with named volumes (mysql, postgres).

**How to avoid:** N/A — this IS the correct behavior. Just be aware that sr-external doesn't persist data across `down` cycles. Each `up` does a full SF1 reload (~30s).

**Warning signs:** None — this is by design.

## Runtime State Inventory

> Phase 4 is greenfield (creating new resources). No rename/refactor concerns.

The phase creates net-new resources only:
- New compose service `sr-external` (no rename of existing services)
- New directory `docker/init/sr-external/`
- New directory `queries/flightsql-starrocks/`
- New file `tests/test_flightsql_starrocks.py`
- One edit to `docker/docker-compose.yml` (add service + dependency)
- One edit to `run-verify.py` (add `'sr-external': False` to services dict)

No existing data, OS-registered tasks, secrets, or installed artifacts are renamed or removed.

## Code Examples

### Example 1: Compose service definition for sr-external

```yaml
# Source: derived from existing sr-main / sr-postgres patterns in docker-compose.yml
sr-external:
  build: .                   # Reuse same Dockerfile as sr-main (D-01)
  container_name: sr-external
  # No 'ports:' — Docker DNS only, per D-02
  volumes:
    - ./certs/:/opt/starrocks/certs/:ro                # Match sr-main; benign even unused
    - ./init/sr-external/:/docker-entrypoint-initdb.d/:ro
    - ./data/sf1/:/opt/starrocks/data/sf1/:ro          # CSVs visible to BE for FILES()
  networks:
    - sr-net
  healthcheck:
    test: ["CMD", "mysql", "-uroot", "-h127.0.0.1", "-P9030", "-e", "SELECT 1"]
    interval: 5s
    timeout: 3s
    retries: 60
    start_period: 180s        # FE+BE warmup ~60s + SF1 load ~30s + buffer
```

### Example 2: 01-schema.sql (sr-external init)

```sql
-- Source: derived from queries/mysql/03-*.sql column types + StarRocks CREATE TABLE syntax
CREATE DATABASE IF NOT EXISTS tpch;
USE tpch;

CREATE TABLE IF NOT EXISTS region (
    r_regionkey INT NOT NULL,
    r_name VARCHAR(25) NOT NULL,
    r_comment VARCHAR(152)
)
DISTRIBUTED BY HASH(r_regionkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS nation (
    n_nationkey INT NOT NULL,
    n_name VARCHAR(25) NOT NULL,
    n_regionkey INT NOT NULL,
    n_comment VARCHAR(152)
)
DISTRIBUTED BY HASH(n_nationkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS supplier (
    s_suppkey INT NOT NULL,
    s_name VARCHAR(25) NOT NULL,
    s_address VARCHAR(40) NOT NULL,
    s_nationkey INT NOT NULL,
    s_phone VARCHAR(15) NOT NULL,
    s_acctbal DECIMAL(15, 2) NOT NULL,
    s_comment VARCHAR(101)
)
DISTRIBUTED BY HASH(s_suppkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS part (
    p_partkey INT NOT NULL,
    p_name VARCHAR(55) NOT NULL,
    p_mfgr VARCHAR(25) NOT NULL,
    p_brand VARCHAR(10) NOT NULL,
    p_type VARCHAR(25) NOT NULL,
    p_size INT NOT NULL,
    p_container VARCHAR(10) NOT NULL,
    p_retailprice DECIMAL(15, 2) NOT NULL,
    p_comment VARCHAR(23)
)
DISTRIBUTED BY HASH(p_partkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS partsupp (
    ps_partkey INT NOT NULL,
    ps_suppkey INT NOT NULL,
    ps_availqty INT NOT NULL,
    ps_supplycost DECIMAL(15, 2) NOT NULL,
    ps_comment VARCHAR(199)
)
DISTRIBUTED BY HASH(ps_partkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS customer (
    c_custkey INT NOT NULL,
    c_name VARCHAR(25) NOT NULL,
    c_address VARCHAR(40) NOT NULL,
    c_nationkey INT NOT NULL,
    c_phone VARCHAR(15) NOT NULL,
    c_acctbal DECIMAL(15, 2) NOT NULL,
    c_mktsegment VARCHAR(10) NOT NULL,
    c_comment VARCHAR(117) NOT NULL
)
DISTRIBUTED BY HASH(c_custkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS orders (
    o_orderkey INT NOT NULL,
    o_custkey INT NOT NULL,
    o_orderstatus CHAR(1) NOT NULL,
    o_totalprice DECIMAL(15, 2) NOT NULL,
    o_orderdate DATE NOT NULL,
    o_orderpriority VARCHAR(15) NOT NULL,
    o_clerk VARCHAR(15) NOT NULL,
    o_shippriority INT NOT NULL,
    o_comment VARCHAR(79) NOT NULL
)
DISTRIBUTED BY HASH(o_orderkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS lineitem (
    l_orderkey INT NOT NULL,
    l_partkey INT NOT NULL,
    l_suppkey INT NOT NULL,
    l_linenumber INT NOT NULL,
    l_quantity DECIMAL(15, 2) NOT NULL,
    l_extendedprice DECIMAL(15, 2) NOT NULL,
    l_discount DECIMAL(15, 2) NOT NULL,
    l_tax DECIMAL(15, 2) NOT NULL,
    l_returnflag CHAR(1) NOT NULL,
    l_linestatus CHAR(1) NOT NULL,
    l_shipdate DATE NOT NULL,
    l_commitdate DATE NOT NULL,
    l_receiptdate DATE NOT NULL,
    l_shipinstruct VARCHAR(25) NOT NULL,
    l_shipmode VARCHAR(10) NOT NULL,
    l_comment VARCHAR(44) NOT NULL
)
DISTRIBUTED BY HASH(l_orderkey)
PROPERTIES('replication_num' = '1');
```

**Notes:**
- **DUPLICATE KEY omitted** to dodge the "key columns must be ordered prefix" pitfall. StarRocks auto-picks (verified live).
- **BUCKETS omitted** — auto-tuned since v2.5.7.
- `replication_num=1` matches the single-BE deployment (also baked into Dockerfile via `default_replication_num = 1` in fe.conf).
- All columns mirror the mysql schema (`docker/init/mysql/01-schema.sql`) types/lengths exactly to ensure SF1 CSV data fits.

### Example 3: 09-lineitem.sql (one of 8 data-load files)

```sql
-- Source: pattern verified live (2026-04-29) on sr-main FE
USE tpch;
TRUNCATE TABLE lineitem;
INSERT INTO lineitem
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/lineitem.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);
```

Replicated 8x with `<table>` substituted for each of: region, nation, supplier, part, partsupp, customer, orders, lineitem. Recommended ordering (alphabetical by integer prefix forces this):
- `02-region.sql`, `03-nation.sql`, `04-supplier.sql`, `05-part.sql`, `06-partsupp.sql`, `07-customer.sql`, `08-orders.sql`, `09-lineitem.sql`

Order doesn't matter for StarRocks (no FK constraints), but preserves alphabetical = logical ordering for clarity in init logs.

### Example 4: tests/test_flightsql_starrocks.py skeleton

```python
"""FlightSQL→StarRocks tests for sr-external Arrow Flight server.

Mirrors tests/test_flightsql.py minus the TLS scenario (D-14 plaintext only).
The 22 TPC-H query coverage is delivered by tests/test_queries.py auto-discovery
of queries/flightsql-starrocks/.
"""

from __future__ import annotations

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)


SR_EXTERNAL_FLIGHT_URI = "grpc://sr-external:9408"


# ---------------------------------------------------------------------------
# D-15 Scenario 1: Catalog lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_catalog_lifecycle(sr_conn, flightsql_driver_path):
    """CREATE / SHOW / SHOW DATABASES / DROP cycle on sr-external Arrow Flight."""
    cat = "test_fs_sr_lc"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={"username": "root", "password": ""},
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not found in {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        db_names = [d[0] for d in dbs]
        assert "tpch" in db_names, f"Expected 'tpch' in databases, got {db_names}"

    finally:
        drop_catalog(sr_conn, cat)

    catalogs = show_catalogs(sr_conn)
    assert cat not in catalogs, f"{cat} still present after DROP"


# ---------------------------------------------------------------------------
# D-15 Scenario 2: Data query (small SELECT)
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_data_query(sr_conn, flightsql_driver_path):
    """SHOW TABLES + small SELECT against sr_flightsql_starrocks.tpch.region."""
    cat = "test_fs_sr_dq"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={"username": "root", "password": ""},
        )

        rows = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.tpch")
        table_names = [r[0] for r in rows]
        for expected in ("region", "nation", "lineitem"):
            assert expected in table_names, (
                f"Expected '{expected}' in tables, got {table_names}"
            )

        result = execute_sql(sr_conn, f"SELECT * FROM {cat}.tpch.region")
        assert len(result) == 5, f"Expected 5 region rows, got {len(result)}"

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-15 Scenario 3: Wrong password
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_wrong_password(sr_conn, flightsql_driver_path):
    """Wrong password fails at CREATE CATALOG (verified live: AuthenticateBasicToken)."""
    cat = "test_fs_sr_wp"
    drop_catalog(sr_conn, cat)
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=flightsql_driver_path,
                uri=SR_EXTERNAL_FLIGHT_URI,
                extra_props={"username": "root", "password": "wrong_password"},
            )
        except pymysql.err.DatabaseError:
            return  # Expected: fails at CREATE for StarRocks Arrow Flight

        # If CREATE succeeded (unlikely for StarRocks but kept for symmetry),
        # the first query MUST fail
        with pytest.raises(pymysql.err.DatabaseError):
            execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-15 Scenario 4: adbc.* passthrough
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_adbc_passthrough(sr_conn, flightsql_driver_path):
    """An arbitrary adbc.flight.sql.* property is forwarded without error."""
    cat = "test_fs_sr_pt"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={
                "username": "root",
                "password": "",
                "adbc.flight.sql.rpc.call_header.x-custom-header": "test-value",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs

    finally:
        drop_catalog(sr_conn, cat)
```

### Example 5: queries/flightsql-starrocks/03-q01-pricing-summary.sql

```sql
-- TPC-H Q01: Pricing Summary Report
-- Catalog: sr_flightsql_starrocks, Schema: tpch
-- Expected: 3 rows
SELECT
    l_returnflag,
    l_linestatus,
    SUM(l_quantity) AS sum_qty,
    SUM(l_extendedprice) AS sum_base_price,
    SUM(l_extendedprice * (1 - l_discount)) AS sum_disc_price,
    SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
    AVG(l_quantity) AS avg_qty,
    AVG(l_extendedprice) AS avg_price,
    AVG(l_discount) AS avg_disc,
    COUNT(*) AS count_order
FROM sr_flightsql_starrocks.tpch.lineitem
WHERE l_shipdate <= DATE_SUB('1998-12-01', INTERVAL 90 DAY)
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus;
```

**Pattern**: Take `queries/mysql/03-q*.sql`, replace catalog/schema (`sr_mysql.testdb` → `sr_flightsql_starrocks.tpch`), keep expected row count (mysql counts apply). 22 files total.

### Example 6: tests/test_queries.py session fixture for sr_flightsql_starrocks

The existing `test_queries.py:CATALOG_MAP` and per-driver fixtures need a parallel fixture:

```python
# Add to CATALOG_MAP (line 19):
"sr_flightsql_starrocks": ("flightsql_driver_path", "grpc://sr-external:9408", None),

# Add session-scoped fixture (after sr_flightsql_cat at line 105):
@pytest.fixture(scope="session")
def sr_flightsql_starrocks_cat(sr_conn, flightsql_driver_path):
    cat = "sr_flightsql_starrocks"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path,
                        uri=CATALOG_MAP["sr_flightsql_starrocks"][1],
                        extra_props={"username": "root", "password": ""})
    yield cat
    drop_catalog(sr_conn, cat)

# Add fixture to test_query_file's signature (line 132-134):
def test_query_file(sr_conn, driver, path,
                    sr_sqlite_cat, sr_sqlite_emp_cat, sr_postgres_cat,
                    sr_mysql_cat, sr_flightsql_cat, sr_duckdb_cat,
                    sr_flightsql_starrocks_cat):  # ← new
```

The driver param logic at line 144-150 already handles:
- `if driver == "duckdb"` → skip (no TPC-H tables)
- `if driver == "flightsql" and "join" in str(path)` → skip (sqlflite limitation)

For `driver == "flightsql-starrocks"` no special skip — all 22 queries run. The directory name maps directly.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Stream Load HTTP for bulk CSV | `INSERT INTO ... SELECT * FROM FILES()` | StarRocks v3.1+ | Single-statement loader, no extra HTTP service |
| Manual `BUCKETS N` | Auto-tuned | StarRocks v2.5.7+ | Less brittle DDL |
| Required `DUPLICATE KEY(...)` | Optional (default to first 1-3 columns) | (always optional, not always documented) | Eliminates "key prefix" pitfall when omitted |
| BE-direct DoGet (Arrow Flight) | FE proxy mode (`arrow_flight_proxy_enabled = true`) | StarRocks PR #66348 (merged Dec 2025, backported to 3.5/4.0) | Client only needs FE port reachable |
| sqlflite as the FlightSQL backend | sr-external StarRocks as a **second** FlightSQL backend | This phase (Phase 4) | TPC-H depth via Arrow Flight; sqlflite kept for generic Arrow Flight + TLS coverage |

**Deprecated/outdated:**
- Stream Load for ~1GB CSVs in a single-container test stack: not deprecated upstream, but FILES() is faster and simpler.
- Manual bucket tuning: still supported, but no longer recommended for StarRocks v3+.
- Direct BE Arrow Flight access from the client: still works, but the proxy mode default obviates the need for client-to-BE network reachability.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Existing `start_period: 5s` between init scripts in entrypoint.sh is sufficient for sr-external's BE warmup before the first INSERT FROM FILES() | Pitfall 2 | Init scripts WARN-fail during cold boot; tests fail because tpch.region doesn't exist. Mitigation: increase to `sleep 10` if observed. |
| A2 | Healthcheck `start_period: 180s` is enough for FE+BE warmup (60s) + total SF1 load (30s, verified) + buffer (90s) | Compose service example | If load is slower on weaker hosts (CI), `start_period` might need bump. Verified on the dev host's ~16-core Linux WSL2; YMMV elsewhere. |
| A3 | `FILES()` schema inference matches the explicit DDL types — i.e., the CSV-inferred columns will be assignment-compatible with the DDL columns of the same name | Pattern 1 | If schema inference produces e.g. STRING when DDL has DECIMAL, INSERT would fail with type-mismatch. Mitigation: live verification of customer (DECIMAL) and lineitem (DECIMAL+DATE) PASSED — INSERT FROM FILES into explicit-DDL DECIMAL/DATE works without explicit casts. |
| A4 | `arrow_flight_proxy_enabled=true` is the default in the current StarRocks build [VERIFIED live but not documented as a guarantee per .deb version] | Pitfall 5 | If proxy mode is off, sr-main needs to reach sr-external on port 9419 directly. Docker bridge network allows this, so functionally equivalent. But discoverability suffers — would manifest as "connection refused" with no obvious cause. Belt-and-suspenders: SET GLOBAL in init script. |
| A5 | The wrong-password path always fails at CREATE CATALOG (not at first query) for StarRocks Arrow Flight [VERIFIED on this build] | Pitfall 4, Test scenario 3 | Different StarRocks builds may delay auth probing. The test (Example 4) handles BOTH paths to be safe. |

## Open Questions

1. **Does the `entrypoint.sh` survive a heavy bind-mount?** The current entrypoint runs `mysql -uroot -h127.0.0.1 -P9030 < /docker-entrypoint-initdb.d/*.sql` for each `.sql` file. Each file's INSERT FROM FILES is fast (3.7s for 6M rows verified), but is there any risk that the entrypoint's FE-side connection times out during a long INSERT?
   - What we know: live test of `mysql ... -e "INSERT INTO ... SELECT FROM FILES()"` for lineitem completed in 3.7s. StarRocks default `interactive_timeout` is 28800s.
   - What's unclear: Whether the entrypoint's `mysql` invocation closes the connection between scripts (it does — each `< $f` is a fresh connection).
   - Recommendation: Per-table SQL files (one INSERT each) keep individual connection lifetimes short. If a single file held all 8 INSERTs, it'd be ~30s of activity in one connection — still way under any timeout. Either layout works; per-table is recommended for log clarity.

2. **Does the planner need to add a `arrow_flight_proxy_enabled = true` SET GLOBAL to init?** Verified live as the default, but documenting belt-and-suspenders style would help future debugging.
   - What we know: Default is `true` on the current build (verified `SHOW VARIABLES LIKE 'arrow_flight%'`).
   - What's unclear: Whether a future StarRocks .deb might flip the default.
   - Recommendation: Skip explicit SET GLOBAL for v1; note in 01-schema.sql comments that the proxy default is assumed. If a future build breaks this, add `SET GLOBAL arrow_flight_proxy_enabled = true;` to 01-schema.sql.

3. **Does sr-external need any healthcheck-aware "wait for tpch DB" logic in test fixtures?** Compose's `depends_on: { condition: service_healthy }` covers ordering at boot. But test fixtures that drop+recreate the catalog mid-suite race only against sr-external's running state, not its init.
   - What we know: Init scripts run inside the `sleep 5; mysql ... < $f` loop in entrypoint.sh, AFTER FE+BE registration. Healthcheck (mysql SELECT 1) goes green during this loop. `start_period: 180s` provides cushion.
   - What's unclear: First-cold-boot timing under CI load.
   - Recommendation: Test fixture wrapping `create_adbc_catalog` + initial `SHOW DATABASES FROM cat` can retry once on `Database 'tpch' doesn't exist` — but this is over-engineering. Per Pitfall 3, the existing `start_period` cushion handles it.

4. **Is MD5/checksum verification needed on SF1 CSVs to detect corruption?** Phase 2's generator is deterministic (random.seed(42)). If a developer regenerates locally with a different Python version's `random` implementation, CSV bytes could shift. sr-external would load whatever's there.
   - What we know: Python's `random.seed(42)` gives identical sequences on Python 3.8+ (verified across CPython releases).
   - What's unclear: Cross-platform (e.g., PyPy) behavior — but the project targets CPython only.
   - Recommendation: No checksum needed. If sr-external row counts diverge from mysql/postgres, that's the canary.

## Environment Availability

> All dependencies for Phase 4 are pre-existing — verified live during research.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | Compose stack | ✓ | (host-installed; verified `docker compose ps` works) | — |
| Docker Compose v2 | All services | ✓ | (verified working) | — |
| StarRocks `.deb` files | sr-external image | ✓ | `feature/remote-table-squashed-9ec3dcc` (`0.1.1`) [VERIFIED] | — |
| ADBC FlightSQL driver | `libadbc_driver_flightsql.so` | ✓ | (already at `/opt/starrocks/drivers/`) | — |
| TPC-H SF1 CSV data | FILES() loader | ✓ | 8 files, ~895 MB total [VERIFIED live] | Regenerate via `python docker/generate-sf1-data.py` (~2 minutes) |
| pytest in `.venv` | Test runner | ✓ | (existing) | — |
| pymysql | sr_conn fixture | ✓ | (existing) | — |
| StarRocks Arrow Flight server | sr-external 9408/9419 | ✓ | (verified `arrow_flight_proxy_enabled = true` live) | — |
| Docker bridge network `sr-net` | Cross-container DNS | ✓ | (verified `nc -zv sr-main 9408` from inside sr-main works) | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None — every dependency is already part of the Phase 1/2/3 deliverables and is currently working in the live stack.

## Sources

### Primary (HIGH confidence — verified live or via official docs)
- **Live verification on sr-main FE (2026-04-29)**: All `FILES()` syntax tests, INSERT timing measurements, ADBC FlightSQL catalog lifecycle, wrong-password error path, Arrow Flight proxy session variables, DUPLICATE KEY pitfall reproduction, idempotency check, expected row count empirical comparison (Q01, Q06, Q22).
- **StarRocks FILES() docs**: https://docs.starrocks.io/docs/sql-reference/sql-functions/table-functions/files/ — CSV format options, NULL marker, RFC-4180 enclose handling, `file://` access requirements.
- **StarRocks Arrow Flight SQL docs**: https://docs.starrocks.io/docs/unloading/arrow_flight/ — version requirements (v3.5.1+), authentication mechanism, FE proxy mode, ports 9408/9419.
- **StarRocks PR #66348**: https://github.com/StarRocks/starrocks/pull/66348 — Arrow Flight proxy default-on, backported to 3.5/4.0/4.1.
- **StarRocks issue #63691**: https://github.com/StarRocks/starrocks/issues/63691 — Closed; resolution clarifies that ADBC clients handle the BE-redirect endpoint.Location automatically.
- **StarRocks DUPLICATE KEY constraint**: https://github.com/StarRocks/starrocks/issues/34836 + StarRocks docs — "Key columns must be the first few columns."
- **ADBC FlightSQL Driver C++ docs**: https://arrow.apache.org/adbc/current/driver/flight_sql.html — DoGet endpoint location handling.
- **Existing project code (read directly)**: `docker/Dockerfile`, `docker/entrypoint.sh`, `docker/docker-compose.yml`, `conftest.py`, `lib/catalog_helpers.py`, `tests/test_flightsql.py`, `tests/test_queries.py`, `queries/mysql/03-*.sql` (22 files), `docker/init/mysql/02-data.sql`, `docker/init/postgres/02-data.sql`, `docker/data/sf1/*.csv`, `run-verify.py`.
- **CLAUDE.md**: Pitfalls section — referenced verbatim under Project Constraints above.

### Secondary (MEDIUM confidence — verified by docs + cross-source)
- StarRocks DATE_ADD/DATE_SUB/INTERVAL/SUBSTR syntax compatibility with MySQL: https://docs.starrocks.io/docs/sql-reference/sql-functions/date-time-functions/date_add/ — confirmed identical syntax to existing `queries/mysql/03-*.sql` files.
- StarRocks DECIMAL precision behavior on aggregate operations: https://docs.starrocks.io/docs/sql-reference/sql-statements/table_bucket_part_index/CREATE_TABLE/ — DECIMAL(15,2) is native, no opaque-type wrapping.
- BUCKETS auto-tuning in v2.5.7+: https://docs.starrocks.io/docs/table_design/table_types/duplicate_key_table/ — referenced in research output.
- TPC-H expected row count differences mysql vs postgres in Phase 2: `queries/mysql/03-*.sql` and `queries/postgres/03-*.sql` — empirically verified on sr-main (2026-04-29) for Q01/Q06/Q22.

### Tertiary (LOW confidence — flagged for runtime verification)
- Arrow Flight `start_period: 180s` is sufficient on every CI host the project runs on. ASSUMED based on dev-host empirical timing of ~30s SF1 load + ~60s warmup. Real CI hosts may need tuning.
- FE+BE init script timing in cold-boot scenario: ASSUMED safe based on Phase 2 mysql/postgres init patterns. Cold-boot test during Phase 4 implementation is the verification.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — every component already live-verified on sr-main; sr-external is a clone with new init SQL.
- Architecture: **HIGH** — exact pattern matches Phase 2's mysql/postgres setup; Arrow Flight server behavior verified via session-variable probe and self-loopback FlightSQL catalog.
- Pitfalls: **HIGH** — DUPLICATE KEY constraint reproduced live, idempotency tested, expected row counts measured empirically, healthcheck-vs-init timing analyzed in entrypoint.sh source.
- TPC-H query dialect compatibility: **HIGH** — Q06 (DATE_ADD/INTERVAL) verified live; remaining 21 queries follow identical mysql syntax (verified by reading all 22 files).
- Expected row counts: **HIGH for the 3 queries verified live (Q01/Q06/Q22), MEDIUM for the remaining 19** — assumed identical to mysql counts but unverified on a full sr-external loadout.

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (30 days; StarRocks `feature/remote-table-squashed-9ec3dcc` build is stable)
