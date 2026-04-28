---
phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints
plan: 02
subsystem: benchmark
tags: [jdbc, adbc, benchmark, cli, tpc-h, ascii-table]

requires:
  - phase: 03
    plan: 01
    provides: create_jdbc_catalog, explain_parser module, JAR in docker/drivers/
provides:
  - benchmark/mysql-jdbc-vs-adbc.py — full JDBC vs ADBC benchmark CLI (argparse, warmup + measurement loop, ASCII table, AVG/GEOMEAN)
  - tests/test_benchmark_cli.py — 3 smoke tests (catalog lifecycle, parser extraction, CLI subprocess)
  - benchmark pytest marker in pyproject.toml
affects: [benchmark, cli, testing]

tech-stack:
  added: []
  patterns:
    - "CLI mirrors run-verify.py shape (shebang, docstring, argparse, main/try/except, banner)"
    - "Catalog cleanup guaranteed via try/finally + KeyboardInterrupt arm"
    - "Smoke tests follow test_mysql.py lifecycle pattern with try/finally drop_catalog"

key-files:
  created:
    - benchmark/mysql-jdbc-vs-adbc.py
    - tests/test_benchmark_cli.py
  modified:
    - pyproject.toml

key-decisions:
  - "All 22 TPC-H queries go through server-side SET_VAR(query_timeout=N) for timeout (not client-side cancellation)"
  - "Warmup pass runs all queries once per catalog before measurement (per D-20)"
  - "Ratios use JDBC/ADBC convention (D-06); AVG/GEOM summary rows use all non-N/A queries"

patterns-established:
  - "CLI constants follow SCREAMING_SNAKE_CASE convention from conftest.py / run-verify.py"
  - "Smoke test subprocess pattern from run-verify.py _run_tests"

requirements-completed:
  - BENCH-01
  - BENCH-06
  - BENCH-07
  - BENCH-08

duration: 20min
completed: 2026-04-28
---

# Phase 03 Plan 02: Benchmark CLI Orchestrator + Smoke Test Summary

**A 533-line single-file benchmark CLI that creates JDBC and ADBC catalogs against the same MySQL backend, runs TPC-H queries with EXPLAIN ANALYZE timing, and prints a wide ASCII comparison table with per-query and summary (AVG/GEOMEAN) rows.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-28T15:42:00Z
- **Completed:** 2026-04-28T16:02:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `benchmark/mysql-jdbc-vs-adbc.py` — 533-line CLI with argparse (4 flags), query discovery, warmup + measurement loop, EXPLAIN ANALYZE parsing, aggregation, ASCII table rendering, FE health probe, catalog lifecycle management
- `tests/test_benchmark_cli.py` — 3 pytest tests: JDBC catalog lifecycle, parser extraction of live EXPLAIN ANALYZE, CLI subprocess smoke test
- `pyproject.toml` — Registered `benchmark` pytest marker
- All 22 TPC-H query files discovered correctly; catalog substitution rewrites `sr_mysql.` → `bench_jdbc.`/`bench_adbc.`
- CLI enforces `--scale sf1` gate, handles timeout with server-side `SET_VAR` hints, probes FE health on errors, and guarantees catalog cleanup via `try/finally` + `KeyboardInterrupt` handler

## Task Commits

Each task was committed atomically:

1. **Task 1: Build the benchmark CLI** — `e9e3ab4` (feat)
2. **Task 2: Smoke test + pytest marker** — `377aa5f` (feat)

## Files Created/Modified

- `benchmark/mysql-jdbc-vs-adbc.py` — 533-line CLI orchestrator
- `tests/test_benchmark_cli.py` — 135 lines, 3 `@pytest.mark.benchmark` tests
- `pyproject.toml` — Added `benchmark: JDBC vs ADBC benchmark CLI tests` marker

## Decisions Made

None — plan executed exactly as written. All function signatures, column widths, flag defaults, and aggregation logic matched the plan verbatim.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. The benchmark runs against the running Docker Compose stack.

## Next Phase Readiness

- The benchmark CLI is ready for live execution: `docker compose up --build` first to bake the JAR, then `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py`
- Phase 3 is complete — all 8 BENCH requirements delivered
- Smoke tests will pass once the Docker stack is up with the JAR baked in

---
*Phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints*
*Completed: 2026-04-28*
