# Phase 3: Compare MySQL JDBC vs ADBC Reproducible Benchmark CLI — Context

**Gathered:** 2026-04-28
**Status:** Ready for planning

<domain>
## Phase Boundary

A reproducible benchmark CLI tool (`benchmark/mysql-jdbc-vs-adbc.py`) that creates separate JDBC and ADBC MySQL catalogs in StarRocks, runs matched TPC-H queries against both, parses EXPLAIN ANALYZE output for scan-node and total execution times, and prints a comparison ASCII table with timing, speedup ratios, and GEOMEAN/AVG summaries. Parametrizable by TPC-H scale factor and query subset.

**In scope:** MySQL backend only. JDBC and ADBC catalog types. TPC-H queries from `queries/mysql/`. EXPLAIN ANALYZE-based timing. ASCII table output.

**Out of scope:** Other backends (PostgreSQL, FlightSQL, DuckDB, SQLite), other catalog types, performance benchmarking beyond MySQL, CI integration, JSON report output.
</domain>

<decisions>
## Implementation Decisions

### CLI Interface & Workflow
- **D-01:** Single command with argparse flags: `./benchmark/mysql-jdbc-vs-adbc.py --scale sf1 --queries 1,2,3 --runs 3`. One entry point, everything controlled via flags.
- **D-02:** CLI lives at `benchmark/mysql-jdbc-vs-adbc.py` (project root, alongside `run-verify.py`).
- **D-03:** Auto-create both JDBC and ADBC catalogs before benchmark, auto-drop after. Self-contained and reproducible by default. Catalog names: `bench_jdbc` and `bench_adbc`.
- **D-04:** CLI flags: `--scale` (default sf1), `--queries` (comma-separated query numbers, default all 22), `--runs` (measurement runs, default 3), `--timeout` (per-query timeout seconds, default 60).

### Output Table Format & Metrics
- **D-05:** One wide ASCII table with columns: Query | JDBC total (ms) | ADBC total (ms) | Total ratio | JDBC scan avg (ms) | ADBC scan avg (ms) | Scan ratio.
- **D-06:** Ratio = JDBC_time / ADBC_time (ADBC speedup). 2.0 means ADBC is 2x faster. 0.5 means JDBC is 2x faster.
- **D-07:** Two comparison levels: **Total** = full EXPLAIN ANALYZE execution time per catalog. **Scan** = per-scan-node time ratios averaged across matching nodes.
- **D-08:** Scan nodes are matched between JDBC and ADBC plans using fragment ID (ADBC_SCAN nodes lack table names; they have `id=` fields). ADBC_SCAN nodes have fields: `id`, `Estimates`, `TotalTime` (with CPUTime, ScanTime components), `OutputRows`, `SubordinateOperators`.
- **D-09:** Scan ratio aggregation: average of per-node JDBCScanNode_time / ADBCScanNode_time ratios. Each matched node pair contributes equally.
- **D-10:** Table sorted by query number (Q1–Q22). Two summary rows at bottom: AVG (arithmetic mean of ratios) and GEOMEAN (geometric mean — standard for normalized benchmarks).
- **D-11:** Row count mismatches between JDBC and ADBC are logged to stderr, not shown in the table.
- **D-12:** The JDBC and ADBC catalogs hit the **same MySQL backend container** (`sr-mysql:3306/testdb`), same database. Any timing difference is purely catalog overhead.

### JDBC Catalog Setup & Configuration
- **D-13:** JDBC driver: MySQL Connector/J (`mysql-connector-j`). JAR file placed in `docker/drivers/` alongside ADBC `.so` files, baked into StarRocks container image via Dockerfile COPY.
- **D-14:** JDBC catalog created with: `CREATE EXTERNAL CATALOG bench_jdbc PROPERTIES(type='jdbc', jdbc_uri='jdbc:mysql://sr-mysql:3306/testdb', driver_url='/opt/starrocks/drivers/mysql-connector-j-*.jar', ...)`. Standard StarRocks JDBC catalog pattern.
- **D-15:** ADBC catalog uses existing `mysql_driver_path` pattern from conftest.py (`/opt/starrocks/drivers/libadbc_driver_mysql.so`, URI `mysql://root:testpass@sr-mysql:3306/testdb`).

### Timing, Measurement & Stats
- **D-16:** Timing method: parse EXPLAIN ANALYZE text output for both total execution time and per-scan-node times. Regex-based extraction from plan text. StarRocks-specific but reliable for this benchmark.
- **D-17:** EXPLAIN ANALYZE parsing is correctness-critical. If parsing fails, it is a tool bug — no fallback to client-side timing. The tool must parse the plan output successfully for every query.
- **D-18:** Run strategy: warm-up run + 3 measurement runs per query per catalog. Report average of measurement runs. Warm-up accounts for cold caches and connection establishment.
- **D-19:** Per-query timeout: fixed 60 seconds. Timeout hit → mark ratio as N/A in table, log to stderr, continue with remaining queries.
- **D-20:** Warm-up runs all 22 queries once on each catalog before starting measurement. One warm-up pass total (not per-query warm-up).

### Query Set Selection & Parametrization
- **D-21:** Queries loaded from `queries/mysql/` directory (22 TPC-H .sql files). Same files used by existing `test_queries.py`.
- **D-22:** Scale factor parametrization: `--scale` flag controls catalog data size via different URI/database. Default SF1. Queries are the same SQL files across scales.
- **D-23:** Query subset: `--queries 1,3,5` runs only specified TPC-H query numbers. Default: all 22.
- **D-24:** Scale factor impacts docker-compose healthcheck `start_period` — larger scales mean longer CSV generation and data loading, which the tool may need to document or the compose file may need to be tuned per scale.

### Error Handling & Failure Modes
- **D-25:** Query failure on one catalog → mark ratio as N/A, log full error details to stderr, continue with remaining queries. Don't abort the benchmark.
- **D-26:** EXPLAIN ANALYZE parse failure → must not happen. The parser is the verification mechanism. If StarRocks changes its plan output format, the tool must be updated before it can run.
- **D-27:** Row count mismatch between JDBC and ADBC → log to stderr with both counts and query name. Continue running. This is a data correctness signal, not a fatal error.

### Agent's Discretion
- Exact regex patterns for EXPLAIN ANALYZE parsing (must handle the plan format shown in discussion: `TotalTime: Xms`, `ScanTime: Xms`, `OutputRows: N`, fragment `id=N`)
- ASCII table rendering library or custom implementation
- Warm-up pass ordering (JDBC first or interleaved)
- Exact CREATE CATALOG SQL for JDBC (property names — StarRocks JDBC catalog syntax)
- CSV generation and data loading for non-SF1 scale factors (Phase 2 infrastructure provides SF1; larger scales are future work)
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — Key Decisions: Docker Compose approach, driver path conventions
- `.planning/REQUIREMENTS.md` — v1/v2 requirements, out of scope
- `.planning/ROADMAP.md` — Phase 3 depends on Phase 2 (SF1 data must be loaded)

### Phase 2 Output (Phase 3 builds on this)
- `queries/mysql/` — 22 TPC-H query .sql files used as benchmark query source
- `docker/docker-compose.yml` — sr-mysql service definition, healthcheck configuration
- `docker/drivers/` — ADBC .so driver files; JDBC JAR will be added here
- `conftest.py` — MySQL driver path constant (`MYSQL_DRIVER`), sr_conn fixture pattern
- `lib/catalog_helpers.py` — `create_adbc_catalog()`, `drop_catalog()`, `execute_sql()` — JDBC catalog will use same execute_sql pattern
- `tests/test_queries.py` — Query file discovery and execution pattern (parametrization by .sql files)
- `tests/test_mysql.py` — MySQL ADBC catalog lifecycle pattern

### StarRocks EXPLAIN ANALYZE Output Format (from discussion)
- ADBC_SCAN nodes: `id=N`, `Estimates: [row, cpu, memory, network, cost]`, `TotalTime: Xms (Y%) [CPUTime: Xms, ScanTime: Xms]`, `OutputRows: N (N)`, `SubordinateOperators: [list]`
- JDBCScanNode nodes: similar structure with JDBC-specific fields
- Fragment IDs are the matching key between JDBC and ADBC plans (no table names in ADBC_SCAN)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/catalog_helpers.py`: `create_adbc_catalog()`, `drop_catalog()`, `execute_sql()`. JDBC catalog creation follows the same pattern but with different property names. `execute_sql()` works for running EXPLAIN ANALYZE on both catalogs.
- `conftest.py`: `sr_conn` session fixture (pymysql connection to StarRocks). MySQL driver path constant. Catalog fixture pattern (create → yield → drop).
- `tests/test_queries.py`: Query file discovery (`QUERIES_DIR.rglob("*.sql")`) and parametrization pattern. `_strip_comments()` and `_expected_rows()` helpers.
- `docker/docker-compose.yml`: sr-mysql service with healthcheck. Same MySQL container serves both JDBC and ADBC catalogs.
- `docker/Dockerfile`: COPY driver pattern for ADBC .so files. JDBC JAR will follow the same pattern.

### Established Patterns
- Session-scoped catalog fixtures with yield/teardown
- Fixed container-internal paths for drivers (`/opt/starrocks/drivers/`)
- Docker DNS service names for cross-container connections (`sr-mysql:3306`)
- Credential convention: `root`/`testpass` for MySQL

### Integration Points
- Benchmark CLI connects to StarRocks via same `STARROCKS_HOST:STARROCKS_PORT` (published port 9030)
- JDBC catalog → sr-mysql:3306 (Docker DNS, internal)
- ADBC catalog → sr-mysql:3306 (Docker DNS, internal, via ADBC driver)
- Both catalogs share the same testdb database with SF1 TPC-H data
</code_context>

<specifics>
## Specific Ideas

- User explicitly wants **two comparison levels**: scan-node time ratios AND total execution time ratios, both in the same table
- Scan nodes matched by fragment ID from EXPLAIN ANALYZE (not table name, since ADBC_SCAN nodes don't include table names)
- EXPLAIN ANALYZE output format was shared during discussion — the parser must handle `TotalTime`, `ScanTime`, `CPUTime`, `OutputRows`, and `id=` fields from ADBC_SCAN and JDBCScanNode blocks
- EXPLAIN ANALYZE parsing is non-negotiable — it is the verification mechanism, not an optional feature
- GEOMEAN is the standard summary for normalized benchmark numbers — must be included alongside AVG
- Scale factor must eventually affect CSV generation and data loading — docker-compose healthcheck `start_period` needs to scale with data size
</specifics>

<deferred>
## Deferred Ideas

- JSON/CSV machine-readable output — CI integration, future enhancement
- Other backends (PostgreSQL JDBC vs ADBC) — separate benchmark tool
- SF10/SF100 scale factors — requires larger data generation and docker-compose tuning
- Performance benchmarking beyond MySQL — out of scope for Phase 3
- Separate MySQL containers per catalog type — rejected; same container for fair comparison
- Interactive/color terminal output — plain ASCII table is sufficient for v1
</deferred>

---

*Phase: 03-compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints*
*Context gathered: 2026-04-28*
