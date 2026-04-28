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
| 1. Docker Compose Verification Suite | 3/3 | Complete | 2026-04-27 |
| 2. PostgreSQL and MySQL TPC-H SF1 | 1/1 | Complete | 2026-04-28 |
| 3. JDBC vs ADBC Benchmark CLI | 2/2 | Complete | 2026-04-28 |

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

### Phase 3: Compare MySQL JDBC vs ADBC reproducible benchmark — CLI prints ASCII table of query times, row counts, and Nx ratios; parametrizable TPC-H scale factor; parses StarRocks EXPLAIN ANALYZE output across separate JDBC/ADBC catalogs and matched query sets

**Goal:** A reproducible single-command CLI at `benchmark/mysql-jdbc-vs-adbc.py` that creates separate JDBC (`bench_jdbc`, MySQL Connector/J 9.3.0) and ADBC (`bench_adbc`) catalogs against the same `sr-mysql:3306/testdb` backend, runs all 22 TPC-H queries against both via `EXPLAIN ANALYZE`, parses Summary.TotalTime and per-scan-node times (matched by operator id), and prints a wide ASCII table with columns Query / JDBC total (ms) / ADBC total (ms) / Total ratio / JDBC scan (ms) / ADBC scan (ms) / Scan ratio plus AVG and GEOMEAN summary rows. Catalogs are auto-created on startup and auto-dropped on exit (including Ctrl+C); per-query timeout is enforced server-side via `SET_VAR(query_timeout=N)`. Parametrizable by `--scale` (sf1 only in v1), `--queries` (subset selection), `--runs` (default 3 + 1 warmup pass per catalog), `--timeout` (default 60s).

**Requirements**: BENCH-01, BENCH-02, BENCH-03, BENCH-04, BENCH-05, BENCH-06, BENCH-07, BENCH-08 *(local Phase-3-only IDs; not added to REQUIREMENTS.md per RESEARCH.md A2)*
**Depends on:** Phase 2

**Success Criteria** (what must be TRUE):
  1. User runs `bash docker/fetch-jdbc-jar.sh` once and `docker/drivers/mysql-connector-j-9.3.0.jar` exists (gitignored, mirrors the `.so` driver convention); after `docker compose up --build`, the JAR is at `/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar` inside the sr-main container.
  2. User runs `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py` with no flags and the CLI runs all 22 TPC-H queries against `bench_jdbc` and `bench_adbc` (one warmup pass per catalog + 3 measurement runs per query per catalog), prints the comparison table, and exits 0.
  3. The output table has rows for Q01–Q22 sorted by query number, columns matching D-05, ratio = JDBC/ADBC (D-06), `N/A` cells where any run timed out (D-19, D-25), and AVG + GEOMEAN summary rows at the bottom (D-10).
  4. Row count mismatches between JDBC and ADBC are logged to stderr only (D-11, D-27) — never shown in the table.
  5. After the CLI exits (success, failure, or Ctrl+C), `SHOW CATALOGS` does not list `bench_jdbc` or `bench_adbc` (auto-drop, including in `KeyboardInterrupt` arm).
  6. `pytest -m benchmark` runs the smoke test in `tests/test_benchmark_cli.py` and exits 0; the existing 35+ test suite continues to pass without regression.

**Plans:** 2 plans

Plans:
- [x] 03-01: Foundations — JDBC catalog helper (`lib/catalog_helpers.create_jdbc_catalog`), EXPLAIN ANALYZE parser module (`benchmark/explain_parser.py` with `parse_summary_total`, `parse_scan_nodes`, `with_timeout_hint`), JAR fetch script (`docker/fetch-jdbc-jar.sh`), CLAUDE.md prerequisites bullet **(BENCH-02, BENCH-03, BENCH-04, BENCH-05)**
- [x] 03-02: Benchmark CLI — `benchmark/mysql-jdbc-vs-adbc.py` orchestrator (argparse, warmup + measurement loop, ASCII table renderer, AVG/GEOMEAN summary, error handling, FE health probe), smoke test (`tests/test_benchmark_cli.py`), `benchmark` pytest marker, end-to-end verification through live stack **(BENCH-01, BENCH-06, BENCH-07, BENCH-08)**

### Phase 4: FlightSQL TPC-H queries against external StarRocks with Arrow Flight ports

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 3
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 4 to break down)
