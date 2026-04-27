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
- [ ] 01-01: Docker Compose Foundation — `docker-compose.yml`, StarRocks Dockerfile (from `.deb` with baked-in ADBC drivers), backend service definitions (PostgreSQL, MySQL, FlightSQL/SQLite) with healthchecks and init SQL, adapted conftest.py using Docker DNS service names, retires `lib/docker_backends.py` and `lib/starrocks.py`. All 35 existing tests pass. **(DC-01, DC-02, DC-03, DC-04, VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-06, VAL-07)**
- [ ] 01-02: TPC-H Depth — TPC-H schema and seed data loaded into all 5 backends, externalized SQL query files in `queries/` directory, cross-driver JOIN test corpus adapted to Docker service names, query execution engine maps query files to catalogs, PostgreSQL DECIMAL→DOUBLE cast resolution **(DC-05, DC-06, VAL-06)**
- [ ] 01-03: Developer Experience — `run-verify.sh` CLI runner, ship→verify→retest loop script, extended log capture from all Compose services on failure, fast iteration path with subset test mode and container reuse **(DC-07, DC-08, DC-09, DC-10)**

## Progress

**Execution Order:**
Phase 1 executes plans sequentially: 01-01 → 01-02 → 01-03

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Docker Compose Verification Suite | 0/3 | Not started | - |
