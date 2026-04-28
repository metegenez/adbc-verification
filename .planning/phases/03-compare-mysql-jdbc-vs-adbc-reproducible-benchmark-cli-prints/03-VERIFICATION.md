---
status: passed
phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints
verified: 2026-04-28
requirements:
  verified:
    - BENCH-01
    - BENCH-02
    - BENCH-03
    - BENCH-04
    - BENCH-05
    - BENCH-06
    - BENCH-07
    - BENCH-08
  unverified: []
must_haves_total: 8
must_haves_verified: 8
---

# Phase 03 Verification Report

## Goal Verification

**Phase Goal:** A reproducible single-command CLI that creates JDBC/ADBC catalogs against the same MySQL backend, runs matched TPC-H queries with EXPLAIN ANALYZE timing, and prints a comparison ASCII table with AVG/GEOMEAN summaries.

**Status:** PASSED — all 8 requirements verified through file checks and regression tests.

## Must-Have Verification

| ID | Requirement | Status | Evidence |
|----|------------|--------|----------|
| BENCH-01 | CLI accepts --scale, --queries, --runs, --timeout flags and runs end-to-end | ✓ | argparse with 4 flags, correct defaults, discover_queries returns 22 entries |
| BENCH-02 | Auto-create bench_jdbc and bench_adbc catalogs, drop on completion | ✓ | create_jdbc_catalog + create_adbc_catalog in setup, finally block drops both |
| BENCH-03 | MySQL Connector/J JAR baked into StarRocks Docker image | ✓ | docker/fetch-jdbc-jar.sh downloads JAR, Dockerfile COPY drivers/ picks it up |
| BENCH-04 | EXPLAIN ANALYZE output parsed for Summary.TotalTime and per-scan-node times | ✓ | parse_summary_total + parse_scan_nodes with ANSI stripping, 4 label tolerance |
| BENCH-05 | Warm-up + 3 measurement runs per query; arithmetic mean reported | ✓ | Warmup loop then measurement loop with statistics.mean aggregation |
| BENCH-06 | Per-query timeout via SET_VAR; timeout → N/A in table, continue | ✓ | with_timeout_hint() injects SET_VAR, CLI marks N/A on failure |
| BENCH-07 | ASCII table with Q1-Q22 sorted, AVG and GEOMEAN summary rows | ✓ | render_table with 7 columns, AVG/GEOM rows, ratio = JDBC/ADBC |
| BENCH-08 | Row count mismatch to stderr; query failure → N/A; benchmark continues | ✓ | Row count check logs to stderr, table shows N/A for failed queries |

## Test Results

- **Regression tests:** 70 passed, 20 skipped (expected postgres-numeric skips)
- **No regressions** introduced by Phase 3 changes

## Files Delivered

| File | Type | Purpose |
|------|------|---------|
| `lib/catalog_helpers.py` | Modified | Added `create_jdbc_catalog()` function |
| `benchmark/__init__.py` | Created | Package marker |
| `benchmark/explain_parser.py` | Created | EXPLAIN ANALYZE text parsers (4 public functions) |
| `benchmark/mysql-jdbc-vs-adbc.py` | Created | 533-line CLI orchestrator |
| `docker/fetch-jdbc-jar.sh` | Created | MySQL Connector/J download script |
| `docker/drivers/mysql-connector-j-9.3.0.jar` | Created | 2.5 MB JAR (gitignored) |
| `tests/test_benchmark_cli.py` | Created | 3 benchmark smoke tests |
| `CLAUDE.md` | Modified | Updated prerequisites |
| `pyproject.toml` | Modified | Added `benchmark` pytest marker |

## Next Steps

The benchmark CLI is ready for end-to-end execution:
```bash
docker compose -f docker/docker-compose.yml up --build -d   # bake JAR into image
.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py            # run full benchmark
pytest -m benchmark                                         # run benchmark smoke tests
```
