---
phase: 01-docker-compose-verification-suite
plan: 02
subsystem: testing
tags: [tpch, queries, cross-join, data-loading, duckdb, sqlite]

requires:
  - phase: 01-01
    provides: Docker Compose environment with 5 services and refactored test framework
provides:
  - Full 8-table TPC-H schema and seed data across all 5 backends
  - Externalized query files in queries/ directory organized by driver
  - Cross-driver federation query (SQLite + PostgreSQL)
  - Pre-baked TPC-H .db files for SQLite, DuckDB, and sqlflite
  - Updated cross-join tests using Docker DNS service names
affects: [03-developer-experience]

tech-stack:
  added: []
  patterns:
    - Placeholder-based query files (sr_<driver> catalog naming convention)
    - TPC-H seed data (5 rows per table)
    - SQLite-compatible init SQL for sqlflite (REAL/TEXT types)

key-files:
  created:
    - queries/sqlite/01-select.sql
    - queries/sqlite/02-join.sql
    - queries/postgres/01-select.sql
    - queries/postgres/02-join.sql
    - queries/mysql/01-select.sql
    - queries/mysql/02-join.sql
    - queries/flightsql/01-select.sql
    - queries/flightsql/02-join.sql
    - queries/duckdb/01-select.sql
    - queries/duckdb/02-join.sql
    - queries/cross-join/sqlite-postgres-join.sql
    - docker/init/sqlflite/init.sql
    - docker/data/tpch_sqlite.db
    - docker/data/tpch_sqlflite.db
  modified:
    - docker/init/postgres/01-schema.sql
    - docker/init/postgres/02-data.sql
    - docker/init/mysql/01-schema.sql
    - docker/init/mysql/02-data.sql
    - docker/generate-data.py
    - docker/data/tpch_duckdb.db
    - docker/data/cross_sqlite_a.db
    - tests/test_cross_join.py

key-decisions:
  - "TPC-H seed data at 5 rows per table (not full SF1) — sufficient for correctness verification"
  - "sqlflite init SQL uses SQLite-compatible types (REAL/TEXT instead of DECIMAL/VARCHAR)"
  - "Query files use placeholder catalog names (sr_sqlite, sr_postgres, etc.) — user substitutes at runtime"
  - "Cross-join tests use employees+customers schema from pre-baked .db files"

requirements-completed: [DC-05, DC-06, VAL-06]

duration: 10min
completed: 2026-04-27
---

# Phase 01 Plan 02: TPC-H Depth Summary

**Full 8-table TPC-H schema with seed data across all 5 backends, externalized query files per driver, and cross-driver federation SQL**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-27T14:12:12Z
- **Completed:** 2026-04-27T14:22:20Z
- **Tasks:** 2
- **Files created:** 13
- **Files modified:** 8

## Accomplishments

- Added part, supplier, partsupp, customer tables to PostgreSQL and MySQL init SQL with 5-row seed data
- Created sqlflite init.sql with SQLite-compatible TPC-H schema (REAL/TEXT types)
- Extended generate-data.py with create_tpch_sqlite(), create_tpch_duckdb(), create_tpch_sqlflite() functions
- 11 query files: 2 per driver (01-select.sql + 02-join.sql) + cross-driver federation query
- Cross-join query joins SQLite employees with PostgreSQL departments via StarRocks federation
- Updated test_cross_join.py: employees schema from pre-baked cross_sqlite_a.db, no subprocess data seeding

## Task Commits

1. **Task 1: TPC-H data loading** - `db2b702` (feat)
2. **Task 2: Query files and cross-join adaptations** - `02da4b8` (feat)

## Files Created/Modified

- `queries/sqlite/` — Region select + orders-lineitem join
- `queries/postgres/` — Region select + orders-lineitem join
- `queries/mysql/` — Region select + orders-lineitem join
- `queries/flightsql/` — Region select + orders-lineitem join
- `queries/duckdb/` — Region select + orders-lineitem join
- `queries/cross-join/sqlite-postgres-join.sql` — Cross-driver federation
- `docker/init/sqlflite/init.sql` — SQLite-compatible TPC-H DDL + seed data
- `docker/data/tpch_sqlite.db` — 8 TPC-H tables, 5 rows each
- `docker/data/tpch_sqlflite.db` — Same content for sqlflite volume mount
- `docker/data/tpch_duckdb.db` — 8 TPC-H tables via duckdb package
- `docker/data/cross_sqlite_a.db` — Updated to employees(id, name, dept_id) schema
- `docker/init/postgres/01-schema.sql` — Added part, supplier, partsupp, customer
- `docker/init/mysql/01-schema.sql` — Added same TPC-H tables
- `tests/test_cross_join.py` — Uses employees+customers tables, no subprocess

## Decisions Made

- TPC-H seed at 5 rows per table (not full SF1) — sufficient for correctness verification
- sqlflite uses SQLite-compatible types (REAL/TEXT) since its backend is SQLite
- Query files use placeholder catalog names (sr_sqlite, sr_postgres, etc.) documented in file headers
- cross_sqlite_a.db now stores employees (id, name, dept_id) for cleaner cross-driver JOIN semantics

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None

## Next Phase Readiness

All 5 backends have full TPC-H schema and seed data. Query files are externalized and versionable. Cross-driver federation SQL is ready for execution. Ready for Plan 01-03 (developer experience — CLI runner, log capture, documentation).

---
*Plan: 01-02*
*Completed: 2026-04-27*
