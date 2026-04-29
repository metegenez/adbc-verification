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
Phase 1: 01-01 → 01-02 → 01-03 (sequential).
Phase 4: 04-04 + 04-05 (wave 1, parallel — independent file scopes) → 04-01 (wave 2, depends on 04-05 for canonical CSVs) → 04-02 + 04-03 (wave 3, depends on 04-01 + 04-05 and 04-01 + 04-04 + 04-05 respectively).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Docker Compose Verification Suite | 3/3 | Complete | 2026-04-27 |
| 2. PostgreSQL and MySQL TPC-H SF1 | 1/1 | Complete | 2026-04-28 |
| 4. FlightSQL TPC-H Against External StarRocks | 0/5 | Pending | — |

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

**Goal:** Add a second StarRocks instance (`sr-external`) to the Docker Compose stack, populate its native StarRocks tables with TPC-H SF1 data via the `FILES()` table function, and verify the StarRocks-native Arrow Flight server path end-to-end. From sr-main, the new ADBC FlightSQL catalog `sr_flightsql_starrocks` connects to `grpc://sr-external:9408` and runs all 22 TPC-H queries plus a 4-scenario test module (lifecycle / data / wrong-password / ADBC pass-through). The phase also performs structural cleanup: dead `lib/` files left behind by Phase 1 (`lib/docker_backends.py`, `lib/starrocks.py`, `lib/tls.py`, `lib/driver_registry.py`) are deleted, the hand-rolled SF1 data generator is replaced with the canonical DuckDB `tpch` extension (~10s SF1 instead of ~2 min), and the per-backend TPC-H query duplicates (`queries/mysql/03-q*.sql`, `queries/postgres/03-q*.sql`) are consolidated into a single canonical home at `queries/tpch/q01.sql..q22.sql` with template-substituted `{catalog}.{db}` placeholders. The existing sqlflite FlightSQL path (`sr-flightsql`, `sr-flightsql-tls`, `tests/test_flightsql.py`) coexists unchanged.

**Requirements:** FS-SR-01, FS-SR-02, FS-SR-03, FS-SR-04, FS-SR-05, FS-SR-06, FS-SR-07, FS-SR-08, FS-SR-09
**Depends on:** Phase 3 (transitively); Phase 2 (SF1 CSV generator and bind-mount pattern)

**Success Criteria** (what must be TRUE):
  1. After `docker compose up -d`, `docker compose ps sr-external` reports `Up (healthy)` within `start_period` (~180s) and a sr-main-side `SHOW DATABASES FROM sr_flightsql_starrocks` lists a `tpch` database with all 8 TPC-H tables populated to canonical SF1 row counts (region=5, nation=25, supplier=10000, part=200000, partsupp=800000, customer=150000, orders=1500000, lineitem=6001215).
  2. From sr-main, `CREATE EXTERNAL CATALOG sr_flightsql_starrocks PROPERTIES("type"="adbc", "driver_url"="...", "uri"="grpc://sr-external:9408", "username"="root", "password"="")` succeeds.
  3. `pytest tests/test_flightsql_starrocks.py -v` exits 0 with all 4 scenarios (lifecycle, data, wrong-password, passthrough) passing.
  4. All 22 canonical TPC-H queries pass against `sr_flightsql_starrocks` (the 5 working postgres queries q04/q12/q13/q16/q21 also pass against `sr_postgres`; all 22 still pass against `sr_mysql`) — driven by `pytest tests/test_queries.py -v`.
  5. The full pre-existing test suite continues to pass with no regression — including `tests/test_flightsql.py` (5 tests) against the unchanged `sr-flightsql` / `sr-flightsql-tls` services. The 35-pytest-test baseline holds.
  6. `lib/` directory contains exactly two files — `__init__.py` and `catalog_helpers.py`. The four retired files (`docker_backends.py`, `starrocks.py`, `tls.py`, `driver_registry.py`) are deleted from disk and removed from any import.
  7. `docker/generate-sf1-data.py` is ≤50 lines and uses the DuckDB `tpch` extension (`INSTALL tpch; LOAD tpch; CALL dbgen(sf=1); COPY <table> TO ...`). A from-scratch run completes in ≤30s on a developer laptop and produces deterministic SF1 CSVs (LF line endings, with header row required by all consumers).
  8. `queries/tpch/q01.sql..q22.sql` exist as the single canonical TPC-H source, using `{catalog}.{db}` template placeholders. The per-backend duplicates `queries/mysql/03-q*.sql` and `queries/postgres/03-q*.sql` no longer exist on disk.
  9. `./run-verify.py docker/starrocks-fe_*.deb docker/starrocks-be_*.deb` completes the full ship→verify→retest cycle, including waiting for `sr-external` in the `_wait_for_healthy()` loop before launching pytest, and prints `✓ PASSED`.

**Plans:** 5 plans

Plans:
- [ ] 04-01: sr-external Compose service + TPC-H schema + SF1 init scripts — `docker/docker-compose.yml` (new `sr-external` service with `build: .`, `:ro` SF1 mount, healthcheck, `start_period: 180s`), `docker/init/sr-external/01-schema.sql` (TPC-H DDL with auto-pick keys per RESEARCH Pitfall 1), `docker/init/sr-external/02-data.sql` (single file with 8 TRUNCATE + INSERT FROM FILES). **(FS-SR-01, FS-SR-02, FS-SR-03)**
- [ ] 04-02: Catalog tests + canonical query loader wiring — `tests/test_flightsql_starrocks.py` (4 scenarios cloned from `test_flightsql.py` minus TLS), `tests/test_queries.py` (extend `CATALOG_MAP` with `sr_flightsql_starrocks`, add `sr_flightsql_starrocks_cat` session fixture, add `CANONICAL_BACKENDS` + `CANONICAL_SKIPS` per `04-CANONICAL-SPEC.md`). **(FS-SR-04, FS-SR-05, FS-SR-06)**
- [ ] 04-03: Integration + docs — `run-verify.py` `_wait_for_healthy()` services dict (add `'sr-external': False`), `.planning/REQUIREMENTS.md` (add FS-SR-01..09 rows + traceability), `.planning/ROADMAP.md` (this entry's Goal / Requirements / Success Criteria / plan list / Progress row), `CLAUDE.md` (Project Layout updates + Phase 4 subsection + 2 new pitfall callouts + Retired-table deletion + Phase 2 SF1 paragraph re-pointed at DuckDB tpch). **(traceability + docs only — no FS-SR-* implementation)**
- [ ] 04-04: Dead `lib/` cleanup — delete `lib/docker_backends.py`, `lib/starrocks.py`, `lib/tls.py`, `lib/driver_registry.py`; verify nothing in `tests/`, `conftest.py`, `lib/catalog_helpers.py`, or `run-verify.py` imports them; the 35-test baseline + new Phase 4 tests still pass. **(FS-SR-07)**
- [ ] 04-05: Canonical TPC-H + DuckDB SF1 generator — rewrite `docker/generate-sf1-data.py` against the DuckDB `tpch` extension (≤50 LOC, deterministic, LF/no-header CSVs), create `queries/tpch/q01.sql..q22.sql` with `{catalog}.{db}` placeholders + per-backend `-- Expected (backend): N rows` comments per `04-CANONICAL-SPEC.md`, delete `queries/mysql/03-q*.sql` and `queries/postgres/03-q*.sql`, run the calibration step (down -v && up && record actual row counts) to populate the Expected lines. **(FS-SR-08, FS-SR-09)**
