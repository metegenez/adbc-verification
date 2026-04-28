# Phase 3: Compare MySQL JDBC vs ADBC Reproducible Benchmark CLI — Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-28
**Phase:** 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints
**Areas discussed:** CLI Interface & Workflow, Output Table Format & Metrics, JDBC Catalog Setup & Configuration, Timing/Measurement & Stats, Query Set Selection & Parametrization, Error Handling & Failure Modes

---

## CLI Interface & Workflow

| Option | Description | Selected |
|--------|-------------|----------|
| Single command with flags | `./run-benchmark.py --scale sf1 --queries 1,2,3 --runs 3`. One entry point, argparse flags. | ✓ |
| Single command + config file | Flags + TOML/YAML config for reproducibility. | |
| Subcommands | Separate commands for compare, list, etc. | |

**User's choice:** Single command with flags. Named `benchmark/mysql-jdbc-vs-adbc.py` in project root. Auto-create both catalogs, auto-drop after.

---

## Output Table Format & Metrics

| Option | Description | Selected |
|--------|-------------|----------|
| Query | JDBC total | ADBC total | Total ratio | JDBC scan avg | ADBC scan avg | Scan ratio | One wide table with both comparison levels. | ✓ |
| Query | JDBC ms | ADBC ms | Ratio | Rows | Plan details | Wider with plan summaries. | |
| Minimal: Query | JDBC ms | ADBC ms | Ratio | Core comparison only. | |

**User's choice:** One wide table with both total-time and scan-node ratios. Ratio = JDBC/ADBC (speedup). Sort by query number. AVG + GEOMEAN summary rows. Row count mismatches to stderr. Scan nodes matched by fragment ID. Scan ratio = average of per-node time ratios.

---

## JDBC Catalog Setup & Configuration

| Option | Description | Selected |
|--------|-------------|----------|
| MySQL Connector/J | Standard MySQL JDBC driver. | ✓ |
| MariaDB Connector/J | Alternative LGPL driver. | |
| Standard JDBC catalog with driver path | CREATE EXTERNAL CATALOG type='jdbc', driver_url to JAR. | ✓ |
| StarRocks built-in JDBC | May not need external JAR. | |

**User's choice:** MySQL Connector/J. JAR baked into container image in `docker/drivers/` alongside .so files. Both catalogs hit same MySQL container (`sr-mysql:3306/testdb`).

---

## Timing, Measurement & Stats

| Option | Description | Selected |
|--------|-------------|----------|
| Parse EXPLAIN ANALYZE for total + scan times | Regex-based extraction from plan text. | ✓ |
| Client-side wall-clock | Simpler but includes network latency. | |
| Warm-up + 3 measurement runs | First run warms caches, then 3 timed runs, report avg. | ✓ |
| Single run per query | Simpler, faster. | |

**User's choice:** EXPLAIN ANALYZE text parsing for both total time and per-scan-node times. Warm-up + 3 measurement runs. 60s per-query timeout. EXPLAIN ANALYZE parsing must work — no fallback.

---

## Query Set Selection & Parametrization

| Option | Description | Selected |
|--------|-------------|----------|
| All 22 queries from queries/mysql/, scale flag selects data size | Default all 22, `--queries 1,3,5` for subset. Scale changes catalog URI. | ✓ |
| Separate directories per scale | `queries/mysql/sf1/`, `queries/mysql/sf10/`. | |
| Default SF1, controlled by catalog URI | Same MySQL container, possible different database per scale. | ✓ |

**User's choice:** All 22 TPC-H queries from `queries/mysql/`. `--scale sf1` flag. Both catalogs use same MySQL backend.

---

## Error Handling & Failure Modes

| Option | Description | Selected |
|--------|-------------|----------|
| Mark N/A, log to stderr, continue | Shown as N/A in table, error details on stderr. | ✓ |
| Skip query entirely | Omit from table. | |
| Abort benchmark | Fail fast. | |
| Fixed 60s per query | Consistent timeout across all queries. | ✓ |

**User's choice:** Query failure → N/A + stderr, continue. 60s timeout. EXPLAIN ANALYZE parse failure → must not happen (verification bug). Row count mismatches → stderr.

---

## Claude's Discretion

- Exact regex patterns for EXPLAIN ANALYZE parsing
- ASCII table rendering approach
- Warm-up pass ordering (JDBC first or interleaved)
- JDBC CREATE CATALOG SQL property names
- CSV generation for non-SF1 scale factors

## Deferred Ideas

- JSON/CSV machine-readable output
- Other backends (PostgreSQL JDBC vs ADBC)
- SF10/SF100 scale factors
- Color terminal output
- Separate MySQL containers per catalog
