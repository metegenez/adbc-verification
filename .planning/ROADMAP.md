# Roadmap: StarRocks ADBC Built-In Verification Suite

## Overview

Transform the existing 35-test ADBC verification suite from a manual local-StarRocks setup into a fully self-contained Docker Compose environment. A single phase delivers the complete stack: Docker Compose orchestration (StarRocks from shipped DEB + all backend data sources), TPC-H query depth across all five ADBC drivers, cross-driver federation verification, and CLI tooling for the build→ship→verify→retest inner dev loop.

## Phases

- [ ] **Phase 1: Docker Compose Verification Suite** — Self-contained environment: `docker compose up --build` starts StarRocks from `.deb` with all 5 ADBC drivers alongside backend databases with TPC-H data; pytest runs full suite from host; CLI runner orchestrates the ship→verify→retest loop

## Phase Details

### Phase 1: Docker Compose Verification Suite
**Goal**: A single-command, self-contained Docker Compose verification environment where StarRocks (from shipped `.deb` with all 5 ADBC drivers) and all backend data sources (PostgreSQL, MySQL, FlightSQL/SQLite) come up on a Docker bridge network, all 35 existing tests pass, TPC-H queries and cross-driver JOINs execute correctly, and the `run-verify.sh` CLI orchestrates the full build→ship→verify→retest cycle with structured failure diagnostics.
**Depends on**: Nothing (first phase)
**Requirements**: DC-01, DC-02, DC-03, DC-04, DC-05, DC-06, DC-07, DC-08, DC-09, DC-10, VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, VAL-07
**Success Criteria** (what must be TRUE):
  1. User runs `docker compose up --build` and StarRocks FE+BE start in a single container with all 5 ADBC drivers available at `/opt/starrocks/drivers/`, while PostgreSQL, MySQL, and FlightSQL/SQLite backend services come up healthy with TPC-H schema and data pre-loaded, all communicating via Docker DNS service names
  2. User runs `pytest tests/ -v` from the host against the Docker Compose environment and all 35 existing tests pass across all 7 test modules (SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL, cross-join, negative)
  3. User runs an externalized SQL query from the `queries/` directory against any of the 5 ADBC catalogs and receives correct TPC-H query results
  4. User runs a cross-driver JOIN query (e.g., `sr_flightsql.tpch.orders JOIN sr_postgres.tpch.lineitem`) through StarRocks and receives correctly joined results across heterogeneous backends
  5. User runs `./run-verify.sh /path/to/starrocks-fe.deb /path/to/starrocks-be.deb` and the full build→ship→verify→retest cycle executes automatically: DEBs are copied, containers build, healthchecks pass, test suite runs, a report is produced, and container logs are captured on any failure
**Plans**: 3 plans

Plans:
- [x] 01-01: Docker Compose Foundation — `docker-compose.yml`, StarRocks Dockerfile (from `.deb` with baked-in ADBC drivers), backend service definitions (PostgreSQL, MySQL, FlightSQL/SQLite) with healthchecks and init SQL, adapted conftest.py using Docker DNS service names, retires `lib/docker_backends.py` and `lib/starrocks.py`. All 35 existing tests pass. **(DC-01, DC-02, DC-03, DC-04, VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, VAL-07)**
- [x] 01-02: TPC-H Depth — TPC-H schema and seed data loaded into all 5 backends, externalized SQL query files in `queries/` directory, cross-driver JOIN test corpus adapted to Docker service names, query execution engine maps query files to catalogs, PostgreSQL DECIMAL→DOUBLE cast resolution **(DC-05, DC-06, VAL-06)**
- [x] 01-03: Developer Experience — `run-verify.sh` CLI runner, ship→verify→retest loop script, extended log capture from all Compose services on failure, fast iteration path with subset test mode and container reuse **(DC-07, DC-08, DC-09, DC-10)**

## Progress

**Execution Order:**
Phase 1 executes plans sequentially: 01-01 → 01-02 → 01-03

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Docker Compose Verification Suite | 0/3 | Not started | - |

### Phase 2: PostgreSQL and MySQL TPC-H SF1 Data Loading and Queries

**Goal:** Replace TPC-H seed data (5 rows/table) in PostgreSQL and MySQL backends with full Scale Factor 1 data (~1GB, 8M+ total rows), and define all 22 TPC-H benchmark queries as externalized SQL files that execute correctly through the StarRocks ADBC catalog layer.

**Depends on:** Phase 1 (Docker Compose foundation)
**Requirements:** TPC-SF1-01, TPC-SF1-02, TPC-SF1-03, TPC-SF1-04

**Success Criteria** (what must be TRUE):
  1. User runs `cd docker && python generate-sf1-data.py` and 8 CSV files (`region.csv` through `lineitem.csv`) are generated in `docker/data/sf1/` with correct TPC-H SF1 row counts (5, 25, 10K, 200K, 800K, 150K, 1.5M, 6M).
  2. User runs `docker compose up` and PostgreSQL + MySQL containers load SF1 data at startup via COPY/LOAD DATA. Querying `SELECT count(*) FROM lineitem` through StarRocks returns ~6M rows.
  3. User runs `pytest tests/test_queries.py -v` and all 44 TPC-H query files (22 for PostgreSQL, 22 for MySQL) execute through the ADBC catalog layer and return expected row counts.
  4. All 35 existing Phase 1 tests continue to pass after SF1 data is loaded.
  5. Restarting or re-creating containers does not duplicate SF1 data (init scripts are idempotent).
**Plans:** 1 plan

Plans:
- [ ] 02-01: TPC-H SF1 Data Loading and 22-Query Corpus — Python SF1 CSV generator (`docker/generate-sf1-data.py`), rewritten PostgreSQL/MySQL init scripts with COPY/LOAD DATA, 44 TPC-H query SQL files across both backends, docker-compose.yml volume mounts for SF1 data, integration verification run **(TPC-SF1-01, TPC-SF1-02, TPC-SF1-03, TPC-SF1-04)**
