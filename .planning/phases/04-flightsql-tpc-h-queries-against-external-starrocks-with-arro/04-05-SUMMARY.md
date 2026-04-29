---
phase: 04
plan: 04-05
title: Replace SF1 Generator with DuckDB tpch + Canonical TPC-H Query Set
status: complete
started: 2026-04-29T17:46:00Z
completed: 2026-04-29T18:15:00Z
---

## One-Liner
Replaced the 503-line hand-rolled SF1 generator with a 38-line DuckDB `tpch` extension wrapper producing canonical TPC-H SF1 CSVs; consolidated 44 per-backend query duplicates into `queries/tpch/q01..q22.sql` with `{catalog}.{db}` placeholders and per-backend calibrated `Expected` counts.

## Tasks

### T01: Add duckdb>=1.0 dependency
- Added `"duckdb>=1.0"` to `pyproject.toml` dependencies
- Already installed in venv (v1.5.2)

### T02: Rewrite docker/generate-sf1-data.py
- Replaced 503 lines with 38 lines using DuckDB's `INSTALL tpch; LOAD tpch; CALL dbgen(sf=1); COPY <table> TO ...`
- Output: LF line endings, comma-delimited, HEADER TRUE

### T03: Regenerate canonical CSV files
- Fixed ownership trap (UID 999 from prior MySQL run)
- Generated 8 CSV files at canonical TPC-H SF1 row counts
- Verified: no CRLF, all row counts match (lineitem = 6,001,215 + 1 header)

### T04: Create 22 canonical queries under queries/tpch/
- Transformed mysql sources: `sr_mysql.testdb.` → `{catalog}.{db}.` placeholders
- Dropped per-file `-- Catalog:` and old `-- Expected:` lines
- All 22 files pass validation: no stale references, no `-- Skip:` directives

### T05: Calibrate per-backend Expected counts
- Downd-vd and brought up sr-main + postgres + mysql with canonical CSVs
- Created `calib_mysql` and `calib_postgres` ADBC catalogs
- Ran all 22 queries against MySQL, 5 working queries (q04/12/13/16/21) against Postgres
- All 5 Postgres counts matched MySQL — used Form A (`-- Expected: N rows`)
- 17 postgres-skipped queries got Form B (`-- Expected (mysql): N` + `-- Expected (flightsql-starrocks): N`)

### T06: Delete 44 duplicate per-backend query files
- `git rm` deleted `queries/mysql/03-q*.sql` (22) and `queries/postgres/03-q*.sql` (22)
- Phase 1 smoke queries (01-select.sql, 02-join.sql) preserved in both dirs

### T07: Regression test
- 37 passed, 33 deselected, 1 xpassed (FE crash from cumulative ADBC catalog operations required one restart)
- Benchmark CLI updated to use canonical `queries/tpch/` with `{catalog}.{db}` substitution

## Deviations
- **Benchmark CLI fix (unplanned):** `benchmark/mysql-jdbc-vs-adbc.py` and `tests/test_benchmark_cli.py` updated to use canonical `queries/tpch/q*.sql` with `{catalog}.{db}` placeholder substitution. The plan did not account for the benchmark being a consumer of the deleted `queries/mysql/03-q*.sql` files.

## Known Issues
- ADBC MySQL driver heap-corruption crash (q17-adbc-fe-crash) recurred during calibration after ~30 ADBC catalog operations. Restart resolved it. The patched `.so` may not be baked into the current Docker image.

## Cross-Plan Handoff
- 04-01 can proceed: CSVs at `docker/data/sf1/` with HEADER row, ready for `csv.skip_header='1'`
- 04-02 can proceed: canonical queries at `queries/tpch/` with `{catalog}.{db}` placeholders, ready for the loader
