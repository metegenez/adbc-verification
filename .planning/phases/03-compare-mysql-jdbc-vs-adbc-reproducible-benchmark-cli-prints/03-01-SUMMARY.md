---
phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints
plan: 01
subsystem: benchmark
tags: [jdbc, adbc, explain-analyze, parser, mysql-connector-j]

requires:
  - phase: 02
    provides: TPC-H SF1 data in queries/mysql/, sr-mysql Docker service
provides:
  - lib.catalog_helpers.create_jdbc_catalog() — JDBC catalog creation via pymysql
  - benchmark.explain_parser — EXPLAIN ANALYZE text parsers (summary total, scan nodes, timeout hint)
  - docker/fetch-jdbc-jar.sh — idempotent MySQL Connector/J download
  - CLAUDE.md prerequisites updated for JDBC JAR
affects: [benchmark, jdbc, mysql]

tech-stack:
  added: []
  patterns:
    - "JDBC catalog helper follows same shape as create_adbc_catalog"
    - "EXPLAIN ANALYZE parser tolerates all four scan-node labels (ADBC_SCAN, JDBC_SCAN, JDBCScanNode, MysqlScanNode)"

key-files:
  created:
    - benchmark/__init__.py
    - benchmark/explain_parser.py
    - docker/fetch-jdbc-jar.sh
    - docker/drivers/mysql-connector-j-9.3.0.jar (gitignored)
  modified:
    - lib/catalog_helpers.py
    - CLAUDE.md

key-decisions:
  - "JDBC catalog uses `user` key (NOT `username` — ADBC-specific)"
  - "driver_url must be exact path (no glob expansion in StarRocks)"

patterns-established:
  - "create_jdbc_catalog mirrors create_adbc_catalog shape with _escape helper"
  - "Underscore-prefix regex constants for module-private parsers"

requirements-completed:
  - BENCH-02
  - BENCH-03
  - BENCH-04
  - BENCH-05

duration: 12min
completed: 2026-04-28
---

# Phase 03 Plan 01: JDBC Catalog Helper + EXPLAIN ANALYZE Parser + JAR Fetch Summary

**JDBC catalog creation via `lib.catalog_helpers.create_jdbc_catalog()`, verified regex-based EXPLAIN ANALYZE text parser with ANSI stripping and SET_VAR timeout hint injection, and idempotent Maven Central JAR download script.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-04-28T15:30:00Z
- **Completed:** 2026-04-28T15:42:00Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- `create_jdbc_catalog()` in `lib/catalog_helpers.py` — 6-param JDBC catalog creation with docstring noting `user` vs `username` distinction
- `benchmark/explain_parser.py` — 4 public functions: `parse_duration_ns`, `parse_summary_total`, `parse_scan_nodes`, `with_timeout_hint`
- `docker/fetch-jdbc-jar.sh` — idempotent bash script downloading mysql-connector-j-9.3.0.jar (2.5 MB) from Maven Central
- CLAUDE.md Prerequisites updated with JAR fetch step
- All parser regexes verified against live container output (ANSI stripping, duration grammar, scan-node matching)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add `create_jdbc_catalog`** — `b805ff3` (feat)
2. **Task 2: Create EXPLAIN ANALYZE parser module** — `96e5f61` (feat)
3. **Task 3: JAR fetch script + CLAUDE.md update** — `cd3c0b3` (feat)

## Files Created/Modified

- `lib/catalog_helpers.py` — Added `create_jdbc_catalog()` function (38 lines) with JDBC property keys
- `benchmark/__init__.py` — Empty package marker (project convention)
- `benchmark/explain_parser.py` — 122 lines, 4 public functions, 6 module-private regex constants
- `docker/fetch-jdbc-jar.sh` — 50 lines, idempotent bash download script
- `docker/drivers/mysql-connector-j-9.3.0.jar` — 2.5 MB, gitignored, baked into sr-main via existing Dockerfile COPY
- `CLAUDE.md` — Added prerequisite bullet for JAR fetch

## Decisions Made

None — plan executed exactly as written. All regex patterns, function signatures, and file locations matched the plan verbatim.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — the JAR was fetched automatically via `docker/fetch-jdbc-jar.sh` during verification. No external service configuration required.

## Next Phase Readiness

- `create_jdbc_catalog` and `explain_parser` are ready for Plan 02 (CLI orchestrator)
- JAR is in `docker/drivers/` (gitignored) — needs `docker compose up --build` to bake into sr-main image
- Open items for Plan 02: verify actual JDBC scan-node label (parser tolerates all four labels), trigger image rebuild

---
*Phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints*
*Completed: 2026-04-28*
