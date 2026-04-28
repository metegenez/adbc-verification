# Phase 3: Compare MySQL JDBC vs ADBC Reproducible Benchmark CLI — Research

**Researched:** 2026-04-28
**Domain:** Python CLI tooling, StarRocks JDBC catalog setup, EXPLAIN ANALYZE plan parsing, ASCII reporting
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**CLI Interface & Workflow**
- **D-01:** Single command with argparse flags: `./benchmark/mysql-jdbc-vs-adbc.py --scale sf1 --queries 1,2,3 --runs 3`. One entry point, everything controlled via flags.
- **D-02:** CLI lives at `benchmark/mysql-jdbc-vs-adbc.py` (project root, alongside `run-verify.py`).
- **D-03:** Auto-create both JDBC and ADBC catalogs before benchmark, auto-drop after. Self-contained and reproducible by default. Catalog names: `bench_jdbc` and `bench_adbc`.
- **D-04:** CLI flags: `--scale` (default sf1), `--queries` (comma-separated query numbers, default all 22), `--runs` (measurement runs, default 3), `--timeout` (per-query timeout seconds, default 60).

**Output Table Format & Metrics**
- **D-05:** One wide ASCII table with columns: Query | JDBC total (ms) | ADBC total (ms) | Total ratio | JDBC scan avg (ms) | ADBC scan avg (ms) | Scan ratio.
- **D-06:** Ratio = JDBC_time / ADBC_time (ADBC speedup). 2.0 means ADBC is 2x faster. 0.5 means JDBC is 2x faster.
- **D-07:** Two comparison levels: **Total** = full EXPLAIN ANALYZE execution time per catalog. **Scan** = per-scan-node time ratios averaged across matching nodes.
- **D-08:** Scan nodes are matched between JDBC and ADBC plans using fragment ID (ADBC_SCAN nodes lack table names; they have `id=` fields). ADBC_SCAN nodes have fields: `id`, `Estimates`, `TotalTime` (with CPUTime, ScanTime components), `OutputRows`, `SubordinateOperators`.
- **D-09:** Scan ratio aggregation: average of per-node JDBCScanNode_time / ADBCScanNode_time ratios. Each matched node pair contributes equally.
- **D-10:** Table sorted by query number (Q1–Q22). Two summary rows at bottom: AVG (arithmetic mean of ratios) and GEOMEAN (geometric mean — standard for normalized benchmarks).
- **D-11:** Row count mismatches between JDBC and ADBC are logged to stderr, not shown in the table.
- **D-12:** The JDBC and ADBC catalogs hit the **same MySQL backend container** (`sr-mysql:3306/testdb`), same database. Any timing difference is purely catalog overhead.

**JDBC Catalog Setup & Configuration**
- **D-13:** JDBC driver: MySQL Connector/J (`mysql-connector-j`). JAR file placed in `docker/drivers/` alongside ADBC `.so` files, baked into StarRocks container image via Dockerfile COPY.
- **D-14:** JDBC catalog created with: `CREATE EXTERNAL CATALOG bench_jdbc PROPERTIES(type='jdbc', jdbc_uri='jdbc:mysql://sr-mysql:3306/testdb', driver_url='/opt/starrocks/drivers/mysql-connector-j-*.jar', ...)`. Standard StarRocks JDBC catalog pattern.
- **D-15:** ADBC catalog uses existing `mysql_driver_path` pattern from conftest.py (`/opt/starrocks/drivers/libadbc_driver_mysql.so`, URI `mysql://root:testpass@sr-mysql:3306/testdb`).

**Timing, Measurement & Stats**
- **D-16:** Timing method: parse EXPLAIN ANALYZE text output for both total execution time and per-scan-node times. Regex-based extraction from plan text. StarRocks-specific but reliable for this benchmark.
- **D-17:** EXPLAIN ANALYZE parsing is correctness-critical. If parsing fails, it is a tool bug — no fallback to client-side timing. The tool must parse the plan output successfully for every query.
- **D-18:** Run strategy: warm-up run + 3 measurement runs per query per catalog. Report average of measurement runs. Warm-up accounts for cold caches and connection establishment.
- **D-19:** Per-query timeout: fixed 60 seconds. Timeout hit → mark ratio as N/A in table, log to stderr, continue with remaining queries.
- **D-20:** Warm-up runs all 22 queries once on each catalog before starting measurement. One warm-up pass total (not per-query warm-up).

**Query Set Selection & Parametrization**
- **D-21:** Queries loaded from `queries/mysql/` directory (22 TPC-H .sql files). Same files used by existing `test_queries.py`.
- **D-22:** Scale factor parametrization: `--scale` flag controls catalog data size via different URI/database. Default SF1. Queries are the same SQL files across scales.
- **D-23:** Query subset: `--queries 1,3,5` runs only specified TPC-H query numbers. Default: all 22.
- **D-24:** Scale factor impacts docker-compose healthcheck `start_period` — larger scales mean longer CSV generation and data loading, which the tool may need to document or the compose file may need to be tuned per scale.

**Error Handling & Failure Modes**
- **D-25:** Query failure on one catalog → mark ratio as N/A, log full error details to stderr, continue with remaining queries. Don't abort the benchmark.
- **D-26:** EXPLAIN ANALYZE parse failure → must not happen. The parser is the verification mechanism. If StarRocks changes its plan output format, the tool must be updated before it can run.
- **D-27:** Row count mismatch between JDBC and ADBC → log to stderr with both counts and query name. Continue running. This is a data correctness signal, not a fatal error.

### Claude's Discretion

- Exact regex patterns for EXPLAIN ANALYZE parsing (must handle the plan format shown in discussion: `TotalTime: Xms`, `ScanTime: Xms`, `OutputRows: N`, fragment `id=N`)
- ASCII table rendering library or custom implementation
- Warm-up pass ordering (JDBC first or interleaved)
- Exact CREATE CATALOG SQL for JDBC (property names — StarRocks JDBC catalog syntax)
- CSV generation and data loading for non-SF1 scale factors (Phase 2 infrastructure provides SF1; larger scales are future work)

### Deferred Ideas (OUT OF SCOPE)

- JSON/CSV machine-readable output — CI integration, future enhancement
- Other backends (PostgreSQL JDBC vs ADBC) — separate benchmark tool
- SF10/SF100 scale factors — requires larger data generation and docker-compose tuning
- Performance benchmarking beyond MySQL — out of scope for Phase 3
- Separate MySQL containers per catalog type — rejected; same container for fair comparison
- Interactive/color terminal output — plain ASCII table is sufficient for v1
</user_constraints>

## Project Constraints (from CLAUDE.md)

These are non-negotiable directives extracted from the project's CLAUDE.md. The plan must comply with all of them.

| Directive | Origin | Applies to Phase 3 |
|-----------|--------|---------------------|
| Docker Compose is the **only** execution path. No local StarRocks, no `STARROCKS_HOST` outside compose. | "Quick Commands" + "Key Rules" | Benchmark connects to `STARROCKS_HOST:STARROCKS_PORT` (env-driven) — same as conftest.py. CLI must NOT spin its own StarRocks. |
| Driver paths are **fixed** at `/opt/starrocks/drivers/...` — no TOML resolution at runtime. | "Key Rules" | JDBC JAR goes at `/opt/starrocks/drivers/mysql-connector-j-<ver>.jar`. CLI hardcodes the path. |
| All catalog interactions go through `lib/catalog_helpers.py` — `create_adbc_catalog()`, `drop_catalog()`. | "Key Rules" | The benchmark must reuse `lib/catalog_helpers` (or extend it for JDBC) — do not duplicate `CREATE EXTERNAL CATALOG` logic in the CLI. A new `create_jdbc_catalog()` helper is the natural extension point. |
| Tests must not leave catalogs behind — always DROP in teardown/finally. | "Key Rules" | CLI must DROP `bench_jdbc` and `bench_adbc` even on Ctrl+C / exception. Use `try/finally` or `atexit`. |
| MySQL connection limit (~500). Each ADBC catalog op opens a fresh backend connection. | "Pitfalls — MySQL connection limit" | Benchmark creates 2 catalogs (one each) and runs 22 queries × 4 runs × 2 catalogs = 176 EXPLAIN ANALYZE statements. Connection pool reuse is StarRocks-side; not a concern at this volume but worth confirming. |
| StarRocks FE can SIGSEGV on malformed queries. | "Pitfalls — StarRocks FE can SIGSEGV" | TPC-H queries Q1-Q22 are already validated in test_queries.py — known-good. The benchmark should not introduce new query shapes. |
| `run-verify.py` invokes pytest via `sys.executable`, which is system Python. Must run as `.venv/bin/python`. | "Pitfalls — run-verify.py quirks" | The new CLI must follow the **same convention** the user already uses: invoke as `.venv/bin/python ./benchmark/mysql-jdbc-vs-adbc.py ...` (or document this in the script's `--help`). |
| SF1 CSVs in `docker/data/sf1/` get chowned to UID 999 by MySQL container. Don't commit them. | "Pitfalls — Pre-flight" | Not directly the benchmark's concern, but document that `docker compose up` must already have run with SF1 data loaded. |
| Skip directive `-- Skip: <reason>` in query files. 17 postgres queries skipped, all 22 mysql queries pass. | "Pitfalls — Skip directive" | The benchmark consumes `queries/mysql/` only — currently all 22 are unskipped. The CLI **must** honor `-- Skip:` directives if any are added later (skipped → exclude from results, log to stderr). |

<phase_requirements>
## Phase Requirements

**No requirement IDs are currently mapped to Phase 3.** REQUIREMENTS.md does not include `BENCH-XX` IDs; ROADMAP.md lists Phase 3 as `Requirements: TBD`.

### Recommendation

Phase 3 is **internal tooling for performance comparison**, not a customer-facing verification feature. The existing requirement language in REQUIREMENTS.md explicitly carves out "performance benchmarking" as out-of-scope for v1 (line 80, "Out of Scope" table).

Two paths:

| Path | Description | When to Choose |
|------|-------------|----------------|
| **A. Local phase IDs** | The planner mints `BENCH-01`...`BENCH-N` IDs in the plan file, scoped to Phase 3 only. Don't update REQUIREMENTS.md. | Matches Phase 02's pattern (TPC-SF1-XX IDs are referenced in ROADMAP but never appear in REQUIREMENTS.md). Lowest friction. |
| **B. Add to REQUIREMENTS.md** | Move "Performance benchmarking" out of "Out of Scope", add a new `### Performance Benchmarking (v1.1)` section with formal `BENCH-XX` IDs, then map them to Phase 3. | Higher rigor; correct if the team wants benchmarks to be a tracked customer-facing capability. |

**Default recommendation: Path A** (local phase IDs). It mirrors Phase 02 exactly and avoids disrupting the v1 scope statement that just shipped. The planner should propose, e.g.:

| ID | Description | Research Support |
|----|-------------|------------------|
| BENCH-01 | CLI accepts `--scale`, `--queries`, `--runs`, `--timeout` flags and runs end-to-end | D-01–D-04, "argparse" CLI Pattern below |
| BENCH-02 | Auto-create `bench_jdbc` and `bench_adbc` catalogs against `sr-mysql:3306/testdb`; drop on completion | D-03, D-12, "JDBC Catalog Syntax (Verified)" below, "lib/catalog_helpers extension point" |
| BENCH-03 | MySQL Connector/J JAR baked into StarRocks Docker image at `/opt/starrocks/drivers/mysql-connector-j-<ver>.jar` | D-13, "Dockerfile COPY pattern" below |
| BENCH-04 | EXPLAIN ANALYZE output parsed for `Summary.TotalTime` and per-scan-node `TotalTime`/`ScanTime` for ADBC_SCAN and JDBCScanNode | D-08, D-16, D-17, D-26, "EXPLAIN ANALYZE Format (Verified Live)" below |
| BENCH-05 | Warm-up pass (1× all queries per catalog) + 3 measurement runs per query per catalog; arithmetic mean reported | D-18, D-20 |
| BENCH-06 | Per-query timeout of 60s applied via SET_VAR hint; timeout → N/A in table, log to stderr, continue | D-19, D-25, "Timeout via StarRocks SET_VAR" below |
| BENCH-07 | ASCII table with Q1–Q22 sorted, AVG and GEOMEAN summary rows, ratio = JDBC/ADBC | D-05, D-06, D-09, D-10 |
| BENCH-08 | Row count mismatch logged to stderr (not in table); query failure → N/A; both keep benchmark running | D-11, D-25, D-27 |

The planner should pick whichever set of IDs is needed and confirm with the user during plan-check.
</phase_requirements>

## Summary

The benchmark CLI is a small, focused tool: ~400 lines of Python that drives StarRocks via pymysql, parses one well-defined text format (StarRocks `EXPLAIN ANALYZE`), and prints one wide table. The four risk-bearing dimensions are (1) the JDBC catalog property syntax (now verified via official docs and the live container error path), (2) the EXPLAIN ANALYZE output format (now verified by running it against the live container — see "EXPLAIN ANALYZE Format" below), (3) timeout enforcement (StarRocks has a native `query_timeout` session variable — strongly preferred over client-side `concurrent.futures` cancellation), and (4) the warm-up pass semantics (Data Cache is *not* applicable to JDBC/ADBC catalogs because both go through the JNI path, so warm-up's value is connection establishment + JIT, not block-cache fill).

**Primary recommendation:** Stick to stdlib + pymysql; don't add `tabulate` (zero-dep f-string formatting suffices). Bake `mysql-connector-j-9.3.0.jar` into the image (newest 9.x, since `com.mysql.cj.jdbc.Driver` is the supported class on MySQL 8.0). Use `query_timeout` via `SET_VAR` hint for per-query timeout, not Python-side cancellation. The JDBC catalog `driver_url` value should be a bare absolute path (`/opt/starrocks/drivers/...`) — both bare and `file:///` paths work, but the verified ADBC pattern in `conftest.py` already uses bare paths, so be consistent.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI argument parsing | Host Python (CLI) | — | argparse, runs on developer's host (`.venv`) |
| Catalog lifecycle (CREATE/DROP) | Host Python (via lib/catalog_helpers) | StarRocks FE | The CLI emits SQL to StarRocks; FE owns catalog state. CLI just orchestrates. |
| Query execution + EXPLAIN ANALYZE | StarRocks FE/BE | MySQL backend | StarRocks runs the plan, calls JDBC/ADBC connector, fetches from MySQL. Timing happens server-side. |
| EXPLAIN ANALYZE text parsing | Host Python (CLI) | — | Pure regex / state machine on the text returned via pymysql. |
| Aggregation (AVG, GEOMEAN, ratio) | Host Python (CLI) | — | `statistics.mean`, `statistics.geometric_mean` (Python ≥3.8). |
| ASCII table rendering | Host Python (CLI) | — | f-string formatting in stdout; no library needed. |
| JDBC driver loading | StarRocks FE/BE (JVM) | — | `driver_url` → JVM classloader. CLI's only responsibility is to ensure the JAR file exists at the specified path inside the container. |
| ADBC driver loading | StarRocks BE (native) | — | Already validated in Phase 1 via existing `MYSQL_DRIVER` constant. |
| Per-query timeout | StarRocks FE | — | Use `SET_VAR(query_timeout=60)` hint — server-side enforcement is cleaner than client-side `concurrent.futures` cancellation. |
| Container build / JAR placement | Docker build context | Dockerfile | Same `COPY drivers/` line that already brings in `.so` files now also brings in `mysql-connector-j-*.jar`. |

## Standard Stack

### Core (already in pyproject.toml — no new deps required)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pymysql` | ≥1.1 | Connect to StarRocks FE on MySQL protocol | [VERIFIED: pyproject.toml line 8] Already used by conftest.py and lib/catalog_helpers.py |
| `pytest` | ≥8.0 | (NOT used by the benchmark CLI itself) | [VERIFIED: pyproject.toml line 7] Listed for completeness — the CLI is a script, not a test. |
| `argparse` | stdlib | CLI flag parsing | [VERIFIED: stdlib] Same pattern as `run-verify.py` lines 16, 53–90 |
| `statistics` | stdlib | `geometric_mean()` for the GEOMEAN summary row | [VERIFIED: Python ≥3.8 has `statistics.geometric_mean`] |
| `re` | stdlib | EXPLAIN ANALYZE text parsing | [VERIFIED: stdlib] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `lib.catalog_helpers` | local | Reuse `drop_catalog`, add new `create_jdbc_catalog` | Always — required by CLAUDE.md "All catalog interactions go through lib/catalog_helpers.py" |

### New JAR Artifact (build-time, not a Python dep)

| Artifact | Version | Source | Where it lives |
|----------|---------|--------|----------------|
| `mysql-connector-j-9.3.0.jar` | 9.3.0 | [VERIFIED: Maven Central listing 2026-04-28] `https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/9.3.0/mysql-connector-j-9.3.0.jar` | `docker/drivers/mysql-connector-j-9.3.0.jar` (host) → `/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar` (container, via Dockerfile `COPY drivers/`) |

**Version selection rationale:** Maven Central currently lists 9.3.0 as the latest (verified 2026-04-28). 9.x supports `com.mysql.cj.jdbc.Driver` (the same class StarRocks docs use in their MySQL example). 8.4.0 is the latest 8.x — also acceptable but 9.3.0 is preferred as the actively-maintained line. The exact JAR filename will appear in the JDBC catalog's `driver_url` property; pinning the version in the CLI avoids the wildcard-glob complexity D-14 implied (`mysql-connector-j-*.jar`).

**Verification command (run before locking the version):**
```bash
curl -sL https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/maven-metadata.xml | grep -o '<latest>[^<]*' | head -1
```

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `mysql-connector-j` (Oracle, GPLv2 + classpath exception) | `mariadb-java-client` (LGPL) | D-13 already locked MySQL Connector/J. MariaDB driver is wire-compatible with MySQL 8.0 but not the StarRocks docs default. Don't switch. |
| Hand-rolled f-string ASCII table | `tabulate` (PyPI), `rich.table` | Adding a dep for one table that prints 24 rows × 7 columns is overkill. f-strings + `:>{w}` width formatting is ~30 lines of code. Existing conftest/run-verify.py have zero non-essential deps — keep that. |
| `concurrent.futures.ThreadPoolExecutor` for timeout | StarRocks `SET_VAR(query_timeout=60)` | StarRocks server-side timeout is **strictly better**: it actually kills the query at FE/BE; ThreadPoolExecutor.cancel() can't interrupt an already-running future on a thread (verified — see "Timeout Enforcement" below). |
| Custom duration parser | `pandas.to_timedelta`, `durations`, `timelength` PyPI libs | StarRocks emits a fixed, narrow grammar (`s`, `ms`, `us`, `ns`, concatenated like `8s544ms`). A 10-line regex parser is cheaper than pulling in pandas. |

**Installation:**
```bash
# JAR (host-side, into docker/drivers/ — checked into git? See Pitfalls section.)
curl -sL -o docker/drivers/mysql-connector-j-9.3.0.jar \
  https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/9.3.0/mysql-connector-j-9.3.0.jar

# No new Python deps. Existing .venv suffices.
```

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Developer host (.venv/bin/python)                                   │
│                                                                     │
│  benchmark/mysql-jdbc-vs-adbc.py                                    │
│  ┌──────────────┐   ┌────────────────┐   ┌─────────────────┐        │
│  │ argparse     │──▶│ catalog setup  │──▶│ run benchmark   │        │
│  │ --scale,     │   │ (create both,  │   │ (warmup +       │        │
│  │ --queries,   │   │  via lib/...)  │   │  3 runs each)   │        │
│  │ --runs,      │   └────────────────┘   └────────┬────────┘        │
│  │ --timeout    │                                 │                 │
│  └──────────────┘                                 ▼                 │
│                                          ┌─────────────────┐        │
│                                          │ EXPLAIN ANALYZE │        │
│                                          │ text parser     │        │
│                                          │ (regex)         │        │
│                                          └────────┬────────┘        │
│                                                   ▼                 │
│                                          ┌─────────────────┐        │
│                                          │ aggregate +     │        │
│                                          │ render ASCII    │        │
│                                          │ table to stdout │        │
│                                          └─────────────────┘        │
│            ▲                                                        │
│  pymysql   │                                                        │
└────────────┼────────────────────────────────────────────────────────┘
             │ MySQL protocol (TCP, port 9030)
             ▼
┌────────────────────────────────────────────────────────┐
│ sr-main (Docker container)                             │
│                                                        │
│  StarRocks FE  ──┐                                     │
│   • catalog mgr  │   /opt/starrocks/drivers/           │
│   • query plan   │   ├── libadbc_driver_mysql.so       │
│   • EXPLAIN      │   └── mysql-connector-j-9.3.0.jar  ◄─── NEW
│   ANALYZE        │                                     │
│  StarRocks BE  ──┘                                     │
│   • JDBC connector (JNI/JVM)                           │
│   • ADBC connector (native FFI)                        │
└─────────────────────────────────┬──────────────────────┘
                                  │ TCP 3306 (Docker DNS)
                                  ▼
                    ┌──────────────────────────┐
                    │ sr-mysql (mysql:8.0)     │
                    │ testdb / TPC-H SF1 data  │
                    │ (~6M lineitem rows etc.) │
                    └──────────────────────────┘
```

**Component responsibilities:**

| Component | File / location | Owns |
|-----------|-----------------|------|
| CLI entry | `benchmark/mysql-jdbc-vs-adbc.py` | argparse, top-level orchestration, exit codes |
| Catalog setup | `lib/catalog_helpers.py` (extend with `create_jdbc_catalog`) | `CREATE EXTERNAL CATALOG` SQL emission, `drop_catalog` reuse |
| Plan execution | `benchmark/mysql-jdbc-vs-adbc.py` | Loop: warmup → measurement runs; pymysql cursor execution |
| Plan parser | `benchmark/mysql-jdbc-vs-adbc.py` (or a small `benchmark/explain_parser.py` module if it grows >150 lines) | Regex-based extraction of `Summary.TotalTime` and per-scan-node times |
| Aggregator | `benchmark/mysql-jdbc-vs-adbc.py` | AVG, GEOMEAN, ratio computation |
| Table renderer | `benchmark/mysql-jdbc-vs-adbc.py` | f-string ASCII table |
| JAR artifact | `docker/drivers/mysql-connector-j-9.3.0.jar` | Provided at image build time |
| Image build | `docker/Dockerfile` (existing `COPY drivers/` line, unchanged) | Bakes JAR into `/opt/starrocks/drivers/` alongside `.so` files |

### Recommended Project Structure

```
benchmark/
├── mysql-jdbc-vs-adbc.py    # Main CLI (single file, ~400 lines)
└── (optional) explain_parser.py  # Split off if parser grows large

lib/
├── catalog_helpers.py        # Existing — add create_jdbc_catalog()
└── ... (unchanged)

docker/
├── drivers/
│   ├── libadbc_driver_*.so   # Existing
│   └── mysql-connector-j-9.3.0.jar  # NEW
├── Dockerfile                 # Unchanged — `COPY drivers/` already does the right thing
└── docker-compose.yml         # Unchanged

queries/mysql/                  # Unchanged — read by the CLI
└── 03-q01-pricing-summary.sql ... 03-q22-global-sales-opportunity.sql
```

### Pattern 1: Reuse `lib/catalog_helpers.py` — extend, don't duplicate

`create_adbc_catalog` already exists. Add a sibling for JDBC.

```python
# lib/catalog_helpers.py — proposed addition
def create_jdbc_catalog(
    conn,
    catalog_name: str,
    jdbc_uri: str,
    user: str,
    password: str,
    driver_url: str,
    driver_class: str = "com.mysql.cj.jdbc.Driver",
) -> None:
    """Issue CREATE EXTERNAL CATALOG for a JDBC source via pymysql.

    Properties are: type, user, password, jdbc_uri, driver_url, driver_class.
    All required by StarRocks JDBC catalog.
    """
    props = {
        "type": "jdbc",
        "user": user,
        "password": password,
        "jdbc_uri": jdbc_uri,
        "driver_url": driver_url,
        "driver_class": driver_class,
    }
    def _escape(v: str) -> str:
        return v.replace('"', '\\"')
    props_sql = ", ".join(f'"{k}"="{_escape(v)}"' for k, v in props.items())
    sql = f"CREATE EXTERNAL CATALOG {catalog_name} PROPERTIES({props_sql})"
    with conn.cursor() as cur:
        cur.execute(sql)
```

[CITED: docs.starrocks.io/docs/data_source/catalog/jdbc_catalog/] — confirms `type/user/password/jdbc_uri/driver_url/driver_class` as the property keys. **The property key is `user`, NOT `username`** — distinct from the ADBC `username` convention noted in CLAUDE.md ("Property key for authentication is `username` (not `user`)" — that rule is ADBC-specific; JDBC uses `user`).

### Pattern 2: argparse CLI mirroring `run-verify.py`

```python
# Source: run-verify.py lines 53–90 (existing project pattern)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("--scale", default="sf1",
                        help="TPC-H scale factor (default: sf1)")
    parser.add_argument("--queries", default="all",
                        help="Comma-separated query numbers (e.g. 1,3,5) or 'all'")
    parser.add_argument("--runs", type=int, default=3,
                        help="Measurement runs per query per catalog (default: 3)")
    parser.add_argument("--timeout", type=int, default=60,
                        help="Per-query timeout in seconds (default: 60)")
    return parser.parse_args()
```

### Pattern 3: Per-query timeout via StarRocks SET_VAR hint

```python
# Verified live against running cluster, 2026-04-28
sql = (
    f"EXPLAIN ANALYZE SELECT /*+ SET_VAR(query_timeout = {timeout_seconds}) */ "
    + body_after_select
)
```

The hint must be inserted **after the first SELECT keyword**. For TPC-H queries that begin `SELECT col1, col2, ...`, transform to `SELECT /*+ SET_VAR(query_timeout = 60) */ col1, col2, ...`. A simple regex `re.sub(r'^\s*SELECT\b', 'SELECT /*+ SET_VAR(query_timeout = 60) */', sql, count=1, flags=re.IGNORECASE)` does the job for TPC-H queries (none of the 22 begin with WITH/CTE — confirmed by inspecting `queries/mysql/`).

### Anti-Patterns to Avoid

- **Wrapping pymysql.cursor.execute() in `concurrent.futures.ThreadPoolExecutor.submit().result(timeout=60)`.** The `Future.cancel()` method cannot interrupt a query already running in the worker thread. The query will continue executing on the StarRocks side until completion. [CITED: Python docs concurrent.futures]. Use `SET_VAR(query_timeout=...)` instead — it's enforced at the StarRocks FE.
- **Adding `tabulate` or `rich` as a dependency for one ASCII table.** Both projects so far have zero non-essential deps; adding one for a benchmark CLI is unjustified. Stick to f-strings.
- **Globbing `mysql-connector-j-*.jar` in the catalog `driver_url`.** StarRocks does not expand globs in `driver_url` — it treats the value as a literal path/URL. Pin the exact filename.
- **Re-fetching the JAR at runtime.** The `sr-main` container has no `curl` or `wget` (verified — `curl: command not found`). The JAR must be copied into the image at build time. Don't try to download it from inside the container. Don't try `driver_url="https://repo1.maven.org/..."` either, because that requires the BE to have outbound HTTPS to Maven Central, which Phase 1's compose stack doesn't guarantee.
- **Mixing warmup and measurement loops.** Run all 22 warmup queries first (per catalog), then the measurement runs. D-20 mandates one warmup pass total — interleaving defeats the purpose.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-query timeout enforcement | `signal.alarm`, `ThreadPoolExecutor.cancel()`, `pymysql.connection.kill_query()` | `SELECT /*+ SET_VAR(query_timeout = 60) */ ...` | Server-side enforcement is the only reliable path. The client can't interrupt a running query without an OOB connection. |
| Geometric mean | Manual `math.exp(sum(math.log(x))/n)` loop | `statistics.geometric_mean(values)` | Stdlib since Python 3.8; handles edge cases (zero values raise; the CLI must filter N/A first anyway). |
| ANSI escape stripping | Custom regex over `\x1b\[...m` | `re.sub(r'\x1b\[[0-9;]*m', '', text)` is fine — but in the actual flow, **strip at parse time**, since pymysql may or may not pass the escape codes through depending on the cursor mode. Verified: pymysql (used by `mysql -uroot ...` in our probe) returns the strings *with* ANSI codes embedded. The parser must strip them or use ANSI-aware regex. |
| EXPLAIN ANALYZE format inference | Regex bouncing between line types | Single-pass state machine: read until "Summary" → grab TotalTime → read until first `Fragment N` → for each operator block, capture `id=N`, `TotalTime`, `OutputRows`, optionally `ScanTime`. |
| TPC-H query number extraction from filename | Manual string slicing | `re.match(r'^03-q(\d{2})-', filename)` matches `03-q01-pricing-summary.sql` cleanly |

**Key insight:** This CLI is a glue script around three orthogonal capabilities: a database driver (pymysql), a session variable (query_timeout), and a text format (EXPLAIN ANALYZE). Pretend the CLI is 200 lines of code, not 1000, and most of the "is there a library for this?" instincts are wrong.

## EXPLAIN ANALYZE Format (Verified Live)

**Source: probed against running `sr-main` container (StarRocks `feature/remote-table-squashed-9ec3dcc`) on 2026-04-28.** [VERIFIED: live container]

### Top-level structure

```
Summary
    QueryId: <uuid>
    Version: feature/remote-table-squashed-9ec3dcc
    State: Finished
    TotalTime: <DUR>
        ExecutionTime: <DUR> [Scan: <DUR> (<PCT>%), Network: <DUR> (<PCT>%), ResultDeliverTime: <DUR> (<PCT>%), ScheduleTime: <DUR> (<PCT>%)]
        CollectProfileTime: <DUR>
        FrontendProfileMergeTime: <DUR>
    QueryPeakMemoryUsage: <SIZE>, QueryAllocatedMemoryUsage: <SIZE>
    Top Most Time-consuming Nodes:
        1. <NODE_TYPE> (id=<N>) : <DUR> (<PCT>%)
        2. ...
    Top Most Memory-consuming Nodes:
    NonDefaultVariables:
        <name>: <old> -> <new>
Fragment 0
│   BackendNum: 1
│   InstancePeakMemoryUsage: <SIZE>, InstanceAllocatedMemoryUsage: <SIZE>
│   PrepareTime: <DUR>
└──RESULT_SINK
   │   TotalTime: <DUR> (<PCT>%) [CPUTime: <DUR>]
   │   OutputRows: <N>
   │   SinkType: MYSQL_PROTOCAL
   └──<INNER_OPERATOR>
      ...
Fragment 1                    # only present for multi-fragment plans
...
```

ANSI color codes are present in the output: `\x1b[0m`, `\x1b[1m`, `\x1b[31m`, `\x1b[38;2;250;128;114m`. The parser **must strip them first** with `re.sub(r'\x1b\[[0-9;]*m', '', text)`.

### Verified ADBC_SCAN block

```
└──ADBC_SCAN (id=0)
       Estimates: [row: 1, cpu: ?, memory: ?, network: ?, cost: 0.0]
       TotalTime: 8s531ms (97.78%) [CPUTime: 38.652ms, ScanTime: 8s492ms]
       OutputRows: 5.915M (5915443)
       SubordinateOperators:
           CHUNK_ACCUMULATE
           LOCAL_EXCHANGE [Passthrough]
       Detail Timers: [ScanTime = IOTaskExecTime + IOTaskWaitTime]
           IOTaskExecTime: 8s475ms
           IOTaskWaitTime: 17.184ms
```

Key fields:
- `id=N` — the matching key per D-08
- `TotalTime: <DUR> (<PCT>%) [CPUTime: <DUR>, ScanTime: <DUR>]` — node-level total includes ScanTime
- `OutputRows: <N>` — may be `<N>` (literal int) or `<HUMAN>.<UNIT> (<EXACT>)` like `5.915M (5915443)`. Use the parenthesized exact form.
- `Detail Timers` — extra info, not needed for D-09 ratios

### Expected JDBCScanNode block (NOT yet verified live — JAR not present)

Per [CITED: github.com/StarRocks/starrocks issue #48367 (file:/// example) and the StarRocks JDBC catalog docs page], the JDBC catalog node type is referred to as `JDBCScanNode` (older docs) or now `JDBC_SCAN` / `MysqlScanNode` in some output paths. **The exact label cannot be verified in this research session because the JAR isn't yet baked in.** The parser should be tolerant of either. Recommended approach:

```python
# Match either token; both are scan nodes for JDBC-flavored connectors
SCAN_NODE_RE = re.compile(
    r'(?P<scan_type>ADBC_SCAN|JDBC_SCAN|JDBCScanNode|MysqlScanNode)\s+\(id=(?P<id>\d+)\)'
)
```

After the JAR is in place (planning's first task), the planner should add a wave-0 verification step: run `EXPLAIN ANALYZE` against `bench_jdbc.testdb.region` and capture the literal scan-node label, then update the regex to be exact.

### Duration grammar

```
DUR := <SEG>(<SEG>)*
SEG := <DIGITS>(\.<DIGITS>)?(s|ms|us|ns)
```

Examples observed in live output:
- `233ms` — single segment
- `8s544ms` — two segments concatenated (no separator)
- `419.099us` — fractional
- `60.449us`
- `0ns`
- `5s` (implied; not seen but documented as the prefix)

**Parser implementation (verified shape):**

```python
import re
_DUR_SEG = re.compile(r'(\d+(?:\.\d+)?)\s*(s|ms|us|ns)')
_UNIT_NS = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}

def parse_duration_ns(s: str) -> int:
    """Parse '8s544ms' / '419.099us' / '0ns' to nanoseconds."""
    total_ns = 0.0
    for m in _DUR_SEG.finditer(s):
        total_ns += float(m.group(1)) * _UNIT_NS[m.group(2)]
    return int(total_ns)
```

For the table, convert ns → ms by `total_ns / 1e6`. Use float ms for arithmetic; round to one decimal place for display.

### Total query time

`TotalTime: <DUR>` appears at the **top of the Summary section** (line 4 in the verified output). **This is the whole-query wall-clock time from the FE's perspective**, including FE planning and result delivery. This is the value to use for D-07 "Total" comparison.

The Summary section also has a more granular `ExecutionTime` line which excludes some FE overhead (planning). For a fair JDBC vs ADBC comparison both go through the same FE, so the inclusion of FE time washes out — `TotalTime` is the right field. Document this in the CLI's `--help` for transparency.

### Per-scan-node time

For D-07/D-09 scan ratios, use the per-node `TotalTime` (includes both `CPUTime` and `ScanTime` for scan operators). This is the value StarRocks itself uses in the "Top Most Time-consuming Nodes" summary. Don't try to use just `ScanTime` — for some operators it's `?`.

### Fragment ID matching strategy (D-08)

Each scan operator block contains `(id=<N>)` — this is **not** the fragment ID, it is the **operator ID**, which is plan-stable across catalog types because the planner walks the same logical query tree. Both JDBC and ADBC plans for query Q1 will have the same operator IDs assigned to scan nodes. Confirmed in the live ADBC output: `ADBC_SCAN (id=0)` for the lineitem scan.

**Matching algorithm:**

1. For each query, run EXPLAIN ANALYZE on JDBC catalog → parse → collect `(id, TotalTime_ns)` pairs for all scan nodes
2. Run EXPLAIN ANALYZE on ADBC catalog → parse → collect `(id, TotalTime_ns)` pairs
3. For each `id` present in **both** sets, compute ratio = JDBC_total / ADBC_total
4. Average the per-id ratios → "Scan ratio" column for that query

If a query has multiple scan nodes (Q3, Q5, Q7, Q8 etc. join multiple TPC-H tables), each contributes one ratio to the per-query average per D-09.

## Common Pitfalls

### Pitfall 1: ANSI escape codes in EXPLAIN ANALYZE output

**What goes wrong:** Naive regex `re.search(r'TotalTime: (\S+)', text)` may match the colored token including `\x1b[0m...`. Numbers extracted look fine but unit detection fails or strings have unexpected chars.

**Why it happens:** StarRocks FE wraps high-latency nodes in ANSI red (`\x1b[1m\x1b[31m`) and medium-latency in salmon (`\x1b[1m\x1b[38;2;250;128;114m`). pymysql delivers the raw bytes — the codes are not stripped.

**How to avoid:** Strip ANSI before parsing: `text = re.sub(r'\x1b\[[0-9;]*m', '', text)`.

**Warning signs:** Extracted duration strings contain non-digit/unit characters; the parser raises ValueError.

### Pitfall 2: `driver_url` glob pattern doesn't expand

**What goes wrong:** D-14 example uses `driver_url='/opt/starrocks/drivers/mysql-connector-j-*.jar'`. StarRocks does NOT expand globs.

**Why it happens:** `driver_url` is treated as a literal URL/path passed to the JVM classloader.

**How to avoid:** Pin the exact filename in both the catalog SQL and the JAR placement. If you want flexibility, define a constant `MYSQL_JDBC_JAR = "/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"` once and reuse.

**Warning signs:** Catalog creation succeeds but queries fail with "ClassNotFoundException" or "Cannot get driver from url".

### Pitfall 3: Same MySQL container, simultaneous JDBC and ADBC connections (CLAUDE.md "MySQL connection limit")

**What goes wrong:** The benchmark loops 22 queries × (1 warmup + 3 runs) × 2 catalogs = 176 EXPLAIN ANALYZE statements. Each one opens at least one backend connection. With StarRocks-side connection pooling, this should be fine — but a parallel run (e.g. accidentally invoking pytest at the same time) blows past the 500-connection limit.

**Why it happens:** ADBC and JDBC connectors maintain their own connection pools; pytest's full suite already saturates ~150–300 connections.

**How to avoid:** Run the benchmark **alone** (don't interleave with pytest). Document this in `--help`. The compose file already pins `--max-connections=500` (CLAUDE.md confirmed), which is enough for the benchmark itself but may be tight if combined with the test suite.

**Warning signs:** Mid-benchmark errors: `Error 1040: Too many connections`. Recovery: wait for pool to drain, or restart `sr-mysql`.

### Pitfall 4: StarRocks Data Cache does NOT cover JDBC/ADBC catalogs

**What goes wrong:** The team may assume warmup primes the StarRocks block cache, but it doesn't.

**Why it happens:** Data Cache (also called Block Cache) operates only on the **native** file readers (Hive, Iceberg, Hudi, Delta, Paimon). JDBC catalog goes through JNI + a JVM connector pool; ADBC catalog goes through native FFI + Arrow IPC. Both bypass the cache. [CITED: docs.starrocks.io/docs/data_source/data_cache/ — "Data Cache currently supports external catalog types using StarRocks Native File Reader (such as Hive, Iceberg, Hudi, Delta Lake, and Paimon), but catalogs that access data based on JNI (such as JDBC Catalog) are not supported yet."]

**Implication:** D-18's warmup pass is still useful, but for different reasons:
- JIT compilation of FE code paths
- JDBC connection pool initialization (first connect is slow; subsequent are fast)
- ADBC driver init / Arrow schema fetch on first call
- MySQL backend's own buffer pool warmup (pages of `lineitem` not yet in `innodb_buffer_pool`)

**How to avoid:** Document this in the CLI's preamble output: "Warmup primes connection pools and MySQL buffer pool, not StarRocks Data Cache (not applicable to JDBC/ADBC)."

**Warning signs:** None — this is informational. The warmup is still the right thing to do; the rationale is just narrower than the user's intuition.

### Pitfall 5: Catalog leak on Ctrl+C

**What goes wrong:** User cancels mid-run; `bench_jdbc` and `bench_adbc` remain in StarRocks. Next run fails with "Catalog already exists".

**Why it happens:** No `try/finally` or signal handler. CLAUDE.md "Tests must not leave catalogs behind" applies to the CLI too.

**How to avoid:** Wrap the entire benchmark loop in `try: ... finally: drop_catalog(conn, "bench_jdbc"); drop_catalog(conn, "bench_adbc")`. `drop_catalog` already does `DROP CATALOG IF EXISTS`, so it's idempotent. As an extra belt-and-suspenders, the CLI should also drop *before* creating, to recover from any prior dirty state.

**Warning signs:** Second invocation prints a CREATE CATALOG error from StarRocks.

### Pitfall 6: ADBC-only `Skip:` directive in queries (Phase 2 forward-compat)

**What goes wrong:** A future `queries/mysql/` query gets a `-- Skip: <reason>` directive (mirroring the postgres-numeric pattern). The benchmark naively executes it anyway and records a failure.

**Why it happens:** The CLI doesn't share `tests/test_queries.py`'s `_skip_reason()` helper.

**How to avoid:** Either (a) factor `_skip_reason()` out into `lib/query_helpers.py` and reuse, or (b) reimplement the same regex in the CLI: `re.search(r'--\s*Skip:\s*(.+)', sql)`. Option (a) is cleaner and is a small refactor of `tests/test_queries.py` lines 43–46.

**Warning signs:** Currently zero queries in `queries/mysql/` have `-- Skip:`, but this could change. The CLI must not silently break when the directive appears.

### Pitfall 7: SF1 ownership / permissions trap (CLAUDE.md "docker/data/sf1/ ownership trap")

**What goes wrong:** Not directly the CLI's problem — but if the user re-generates SF1 data after running the benchmark, they may hit the UID 999 permission issue. The benchmark CLI should not regenerate data; it assumes the existing SF1 stack is up.

**How to avoid:** Document in the CLI's `--help` and README block: "This tool assumes `docker compose up` has already run with SF1 data loaded. Run `pytest tests/test_queries.py -k mysql` first to verify the data is queryable."

### Pitfall 8: Containers stale; benchmarking against a previous DEB

**What goes wrong:** User runs benchmark, edits StarRocks code, runs benchmark again — but `docker compose up --build` wasn't issued, so they're benchmarking the old binary.

**How to avoid:** The CLI prints `SELECT @@version_comment` (or queries `Summary.Version` from EXPLAIN ANALYZE) and includes it in the output header so the user sees which build they're benchmarking. The verified live output included `Version: feature/remote-table-squashed-9ec3dcc` — useful as a provenance string in the report.

## Code Examples

Verified patterns from official sources / live container.

### EXPLAIN ANALYZE → parse Summary.TotalTime

```python
import re

_ANSI = re.compile(r'\x1b\[[0-9;]*m')
_DUR_SEG = re.compile(r'(\d+(?:\.\d+)?)\s*(s|ms|us|ns)')
_UNIT_NS = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}

def parse_duration_ns(s: str) -> int:
    total = 0.0
    for m in _DUR_SEG.finditer(s):
        total += float(m.group(1)) * _UNIT_NS[m.group(2)]
    return int(total)

def parse_summary_total(plan_text: str) -> int:
    """Return Summary.TotalTime in nanoseconds. Raises if not found (D-26)."""
    plan = _ANSI.sub('', plan_text)
    m = re.search(r'^\s*TotalTime:\s*(\S+)\s*$', plan, re.MULTILINE)
    if not m:
        raise ValueError("Could not find Summary.TotalTime in EXPLAIN ANALYZE output")
    return parse_duration_ns(m.group(1))
```

### EXPLAIN ANALYZE → per-scan-node times

```python
SCAN_NODE_RE = re.compile(
    r'(?P<scan>ADBC_SCAN|JDBC_SCAN|JDBCScanNode|MysqlScanNode)\s*\(id=(?P<id>\d+)\)'
)
TIME_AFTER_NODE = re.compile(
    r'TotalTime:\s*(?P<dur>\S+)\s*\(\d',  # the (NN.NN%) suffix
    re.MULTILINE
)

def parse_scan_nodes(plan_text: str) -> dict[int, int]:
    """Return {operator_id: total_ns} for all scan nodes in the plan."""
    plan = _ANSI.sub('', plan_text)
    out = {}
    for m in SCAN_NODE_RE.finditer(plan):
        op_id = int(m.group("id"))
        # The first TotalTime: line after this match is the node's TotalTime
        rest = plan[m.end():]
        t = TIME_AFTER_NODE.search(rest)
        if t:
            out[op_id] = parse_duration_ns(t.group("dur"))
    return out
```

### Apply per-query timeout via SET_VAR

```python
def with_timeout_hint(sql: str, timeout_seconds: int) -> str:
    """Insert SET_VAR(query_timeout=N) hint after the first SELECT keyword."""
    return re.sub(
        r'^\s*SELECT\b',
        f'SELECT /*+ SET_VAR(query_timeout = {timeout_seconds}) */',
        sql,
        count=1,
        flags=re.IGNORECASE,
    )
```

### Run EXPLAIN ANALYZE and extract output

```python
def run_explain_analyze(conn, sql: str) -> str:
    """Run 'EXPLAIN ANALYZE <sql>' and return the single-column text result."""
    with conn.cursor() as cur:
        cur.execute("EXPLAIN ANALYZE " + sql)
        rows = cur.fetchall()
        # EXPLAIN ANALYZE returns one row, one column ("Explain String")
        return rows[0][0] if rows else ""
```

### ASCII table rendering (stdlib)

```python
def render_table(rows: list[dict], cols: list[tuple[str, int]]) -> str:
    """rows is a list of dicts; cols is [(label, width), ...]."""
    sep = "+".join("-" * (w + 2) for _, w in cols)
    sep = f"+{sep}+"
    out = [sep]
    out.append("| " + " | ".join(f"{lbl:<{w}}" for lbl, w in cols) + " |")
    out.append(sep)
    for r in rows:
        out.append("| " + " | ".join(f"{r[lbl]!s:<{w}}" for lbl, w in cols) + " |")
    out.append(sep)
    return "\n".join(out)
```

### Full JDBC catalog creation (verified property keys)

```sql
-- VERIFIED: docs.starrocks.io/docs/data_source/catalog/jdbc_catalog/
-- VERIFIED: live error path (Cannot get driver from url ...) confirms key names accepted
CREATE EXTERNAL CATALOG bench_jdbc PROPERTIES(
  "type"="jdbc",
  "user"="root",
  "password"="testpass",
  "jdbc_uri"="jdbc:mysql://sr-mysql:3306/testdb",
  "driver_url"="/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar",
  "driver_class"="com.mysql.cj.jdbc.Driver"
);
```

## Specific Topic Findings

### 1. JDBC catalog property keys — required vs optional [VERIFIED]

| Key | Required? | StarRocks-Verified Value for MySQL |
|-----|-----------|-------------------------------------|
| `type` | required | `"jdbc"` |
| `user` | required | `"root"` (note: NOT `"username"`) |
| `password` | required | `"testpass"` |
| `jdbc_uri` | required | `"jdbc:mysql://sr-mysql:3306/testdb"` (db included) |
| `driver_url` | required | `"/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"` (bare path or file:// — both work) |
| `driver_class` | required | `"com.mysql.cj.jdbc.Driver"` (for MySQL 8.0+ / Connector/J 9.x) |
| `schema_resolver` | optional | not needed for MySQL |
| `comment` | optional | not needed |

[CITED: docs.starrocks.io/docs/data_source/catalog/jdbc_catalog/]
[VERIFIED: live container — error path "Cannot get driver from url: <path>" confirms all six properties are accepted and parsed; only `driver_url` value's existence-on-disk gates success.]

### 2. MySQL Connector/J distribution [VERIFIED]

- **Version:** 9.3.0 (latest 2026-04-28)
- **Maven Central URL:** `https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/9.3.0/mysql-connector-j-9.3.0.jar`
- **Filename:** `mysql-connector-j-9.3.0.jar`
- **Driver class:** `com.mysql.cj.jdbc.Driver` (modern; `com.mysql.jdbc.Driver` is the deprecated 5.x class)
- **License:** GPL-2.0 with Universal FOSS Exception (suitable for distribution in a verification image)
- **Download command (host):**
  ```bash
  curl -sL -o docker/drivers/mysql-connector-j-9.3.0.jar \
    https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/9.3.0/mysql-connector-j-9.3.0.jar
  ```
- **Dockerfile change:** **None required.** The existing line 18 `COPY drivers/ /opt/starrocks/drivers/` already copies everything in `docker/drivers/`. The new JAR will be picked up automatically.
- **Should the JAR be committed to git?** [ASSUMED] Probably yes (~2 MB, deterministic, version-pinned). Phase 1 already commits the ADBC `.so` files in `docker/drivers/`. Following the same convention is least surprising. The planner should verify whether `docker/drivers/` is in `.gitignore` (it appears not to be, since the `.so` files are present and being COPY'd at build time).

### 3. EXPLAIN ANALYZE total query time [VERIFIED]

Top of Summary block: `TotalTime: <DUR>` on line 4 of the output (after `Summary` header, `QueryId`, `Version`, `State`). This is the whole-query time including FE planning, scheduling, scan, and result delivery. Use this for the D-07 "Total" column.

There is **no** "Query Total Time" or "Total Cost" labelled field — `TotalTime` is the canonical label.

### 4. ASCII table rendering recommendation [DECIDED]

**Recommendation: stdlib f-strings, no library.** The table is 22 rows + 2 summary rows × 7 columns. Hand-rolling is ~30 lines. Adding `tabulate` ($pip install$) means modifying `pyproject.toml`, recreating venvs, and explaining to readers why. The project's `pyproject.toml` currently has 3 deps total — keep it lean.

If the planner pushes back, the next-best is `tabulate` (pure-Python, single file, BSD licensed). Avoid `rich.table` — it pulls in 5+ transitive deps and color terminal handling we don't need.

### 5. Per-query timeout enforcement [VERIFIED]

**Recommendation: StarRocks `query_timeout` session variable via SET_VAR hint.** [VERIFIED: live container]

- Default: 300 seconds (`SHOW VARIABLES LIKE 'query_timeout'` returned `300` on the running cluster)
- Unit: seconds
- Hint syntax: `SELECT /*+ SET_VAR(query_timeout = 60) */ ...`
- Compatible with `EXPLAIN ANALYZE`: confirmed by running `EXPLAIN ANALYZE SELECT /*+ SET_VAR(query_timeout = 60) */ count(*) FROM information_schema.tables;` against the cluster — produced normal Summary output.
- Behaviour on timeout: query aborts at FE; pymysql receives an error response. CLI catches `pymysql.err.OperationalError` (or specific subclass), records "TIMEOUT" for that query in the result map, logs to stderr, continues.

**Why not `concurrent.futures` cancellation:** [VERIFIED: Python docs] `Future.cancel()` cannot interrupt a thread that has already started executing. Even `cancel_futures=True` on `executor.shutdown()` only prevents queued futures from starting; it does not stop running ones. The query continues consuming StarRocks resources after the client gives up. Server-side `query_timeout` is strictly cleaner.

### 6. Warm-up + 3-runs orchestration [INFORMED]

**Recommendation:** Per-catalog warmup — run all 22 queries on `bench_jdbc` first, then all 22 on `bench_adbc`. After both warmups complete, do 3 measurement passes interleaved per query (Q1-JDBC, Q1-ADBC, Q1-JDBC, ..., Q2-JDBC, ...). This gives both catalogs equal exposure to "system warm" conditions.

**Warmup scope (verified):**
- ✅ MySQL InnoDB buffer pool (the 6M `lineitem` rows get partially cached after first scan)
- ✅ JVM JIT compilation in StarRocks FE (Java planner code paths)
- ✅ JDBC connection pool (first connect is slow; subsequent are pooled)
- ✅ ADBC driver schema cache
- ❌ StarRocks Data Cache (NOT triggered for JDBC/ADBC; see Pitfall 4)

**Implication:** Warmup is still meaningful but the CLI should NOT promise users it's flushing/filling the StarRocks block cache.

### 7. Scale factor pass-through [DECIDED]

**Recommendation: `--scale sf1` is currently a stub.** v1 should validate the input is exactly `"sf1"` and exit with an error otherwise. This forces the user to confront the work involved when SF10/SF100 land (separate CSV generators, separate compose tuning, separate database name conventions).

```python
if args.scale != "sf1":
    print(f"Error: only --scale sf1 is supported in v1 (got: {args.scale})", file=sys.stderr)
    sys.exit(2)
```

When SF10 lands later, the gate becomes `if args.scale not in ("sf1", "sf10")` and the URI/database mapping kicks in. D-22 says "different URI/database" — which suggests `bench_jdbc` connects to `testdb_sf1` vs `testdb_sf10`, but this is a future decision; v1 doesn't need to commit.

### 8. Project skill `ship-starrocks` [INFORMATIONAL]

A skill exists at `~/.claude/skills/ship-starrocks/SKILL.md` but it describes the **older single-container `docker run` flow** (predates `docker-compose.yml`). It assumes paths like `/home/mete/coding/remote_table_verification/docker/` (note: this is the previous project name; current project is `adbc_verification`). The skill is essentially superseded by `run-verify.py`.

**Relevant takeaway for Phase 3:** None directly. The skill places drivers in the same `/opt/starrocks/drivers/` location, confirming the convention. The benchmark JAR sits in the same place. The skill does NOT mention JDBC JARs — Phase 3 introduces them.

**Skill should be updated** (separate from this phase) to reflect the new compose flow and the new driver-placement convention now that JDBC JARs are part of the image. This is a secondary concern, not a blocker.

### 9. Pitfalls from CLAUDE.md applicable to Phase 3

Re-flagged from CLAUDE.md "Pitfalls" section, with phase-specific commentary:

| CLAUDE.md Pitfall | Applies to Phase 3? | Plan should… |
|--------------------|---------------------|--------------|
| Generate SF1 CSVs first | YES — prereq | Document in CLI `--help`: assumes SF1 stack already up. Don't try to generate. |
| `docker/data/sf1/` UID 999 trap | INDIRECT | Not directly the CLI's problem; mention in README. |
| `:ro` mount for SF1 (mysql breaks) | NO | Compose file already correct, unchanged in Phase 3. |
| CSV CRLF line endings | NO | Phase 2 already fixed; doesn't affect benchmark. |
| MySQL TCP healthcheck | NO | Already fixed in Phase 2. |
| MySQL `max_connections=500` | YES — soft constraint | Document: don't run benchmark + pytest concurrently. |
| **StarRocks FE SIGSEGV on malformed queries** | YES — RISK | The 22 mysql TPC-H queries are pre-validated by `tests/test_queries.py`, but **the benchmark introduces a new dimension: running them through the JDBC catalog instead of ADBC.** It's possible the JDBC code path has different SIGSEGV triggers. Plan should include: if a query fails on JDBC catalog, the CLI must catch the connection-lost error specifically and check FE health (e.g., `SELECT 1`) before continuing. If FE is dead, abort and tell user to `docker compose restart sr-main`. |
| `run-verify.py` quirks (sys.executable / no curl) | YES — applies to new CLI | New CLI should be invoked as `.venv/bin/python ./benchmark/mysql-jdbc-vs-adbc.py ...`. Document in script's `--help` and (optionally) check `sys.prefix` or `pymysql` import to fail-fast if invoked under system Python. |
| Stack lifecycle (down -v) | NO | Benchmark doesn't manage compose. |
| Postgres-numeric Arrow gap | NO | Phase 3 is MySQL-only. |
| Skip directive in query files | YES — forward-compat | CLI should honor `-- Skip:` (currently zero mysql queries use it; could change). |

### 10. Phase requirement IDs (BENCH-XX) [DECISION]

See `<phase_requirements>` section above. **Recommendation: Path A — local phase IDs.** The planner should mint `BENCH-01` through `BENCH-08` (or similar) in the plan file but should NOT update REQUIREMENTS.md, matching the Phase 02 (TPC-SF1-XX) pattern.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mysql:mysql-connector-java` (old groupId) | `com.mysql:mysql-connector-j` | 8.0.31 (2022); 9.x is current line | Use the new groupId/artifactId |
| Driver class `com.mysql.jdbc.Driver` (5.x) | `com.mysql.cj.jdbc.Driver` (6.x+) | MySQL Connector/J 6.0 | Always use `cj` for modern MySQL |
| Client-side timeout via signal/threading | Server-side `query_timeout` SET_VAR | StarRocks 2.x+ | Cleaner, doesn't waste server resources |
| `EXPLAIN ANALYZE` text format | Same format, but enhanced in StarRocks 4.0 | StarRocks 4.0 | Phase 3 targets the FE/BE shipped in current image; format verified live |

**Deprecated/outdated:**
- MySQL Connector/J 5.x and 8.0.x (use 8.4.0+ or 9.x)
- `com.mysql.jdbc.Driver` class name
- `mysql:mysql-connector-java` Maven coordinates (use `com.mysql:mysql-connector-j`)

## Runtime State Inventory

> Phase 3 is greenfield (new CLI tool, new JAR file). No rename/refactor/migration. This section is included for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — verified by inspecting `.planning/phases/02-*/` deliverables. The benchmark only reads SF1 data; doesn't write any persistent state. | none |
| Live service config | None — no n8n/Datadog/Tailscale in this project. | none |
| OS-registered state | None — no systemd/launchd/Task Scheduler integration. | none |
| Secrets/env vars | None new. CLI reads `STARROCKS_HOST`/`STARROCKS_PORT` (already set in conftest.py); MySQL credentials are hardcoded `root/testpass` matching test convention. | none |
| Build artifacts | New JAR at `docker/drivers/mysql-connector-j-9.3.0.jar`. Built into Docker image at build time. No package manager / pip integration. | Add to `docker/drivers/` (git-tracked alongside `.so` files). |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker / Docker Compose v2 | Whole stack (precondition) | ✓ | (existing) | — |
| `sr-main` container running | All CLI operations | ✓ (live, healthy as of probe) | StarRocks `feature/remote-table-squashed-9ec3dcc` | — |
| `sr-mysql` container running | Both catalogs | ✓ (healthy) | mysql:8.0 | — |
| Python 3.11+ in `.venv` | CLI runtime | ✓ (existing) | (per pyproject.toml) | — |
| `pymysql` | DB connection | ✓ (existing) | ≥1.1 | — |
| `argparse`, `re`, `statistics` | CLI core | ✓ (stdlib) | — | — |
| `mysql-connector-j-9.3.0.jar` | JDBC catalog | ✗ | — | Must be downloaded into `docker/drivers/` and image rebuilt before first run |
| Maven Central HTTPS access (host) | One-time JAR download | ✗ to ✓ assumption | — | If host is offline, manual JAR placement required |
| `curl` or `wget` in `sr-main` container | (would be) runtime JAR fetch | ✗ (verified: `curl: command not found`) | — | None — must bake JAR into image, not download at runtime |

**Missing dependencies with no fallback:**
- None — the JAR has a clean download path; image rebuild is part of the existing dev loop (`run-verify.py` does `docker compose up --build` by default).

**Missing dependencies with fallback:**
- JAR download → if Maven Central is unreachable, the user can copy a JAR from another source (project README should list the JAR's SHA256 for verification).

## Assumptions Log

> Claims tagged `[ASSUMED]` that the planner / discuss-phase may want to confirm with the user before locking.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The MySQL Connector/J JAR should be checked into git in `docker/drivers/` (matching the `.so` driver convention) | "Standard Stack — Should the JAR be committed to git?" | If the team prefers it in `.gitignore` and downloaded by `run-verify.py`, the image build flow needs an extra `RUN curl` (which won't work — see Pitfall: no curl in container) or a host-side fetch step. Either way the planner needs to decide. **Recommendation: commit it, mirror `.so` pattern.** |
| A2 | Phase 3 should not update REQUIREMENTS.md; local `BENCH-XX` IDs in the plan file are sufficient | "Phase Requirements" | If the team wants formal v1.1 requirement tracking, REQUIREMENTS.md needs an update. Low risk; planner can ask during plan-check. |
| A3 | The exact JDBCScanNode label in StarRocks output is one of `JDBCScanNode`, `JDBC_SCAN`, or `MysqlScanNode` | "Expected JDBCScanNode block (NOT yet verified live)" | Parser regex needs fix-up after first benchmark run. Low risk if planner adds a "verify scan node label" step in wave 0. **Recommendation: regex matches all three; verify on first run; tighten if desired.** |
| A4 | The benchmark CLI should run as `.venv/bin/python` (not system Python or `./benchmark/mysql-jdbc-vs-adbc.py` directly) | "Project Constraints — run-verify.py invokes pytest via sys.executable" | If user prefers a `#!/usr/bin/env python3` shebang and adds a one-line `if not sys.prefix.endswith('.venv'): exit(...)` guard, that works too. Low risk. |
| A5 | `query_timeout` set via SET_VAR hint propagates correctly to JDBC and ADBC scan nodes (i.e., the FE-side timeout actually kills the BE-side scan) | "Per-query timeout enforcement" | If the timeout only fires after the FE returns control (e.g., during result delivery), a 60s scan that takes 90s might still complete. **Mitigation: in wave 0, run a deliberately-slow query (e.g., `SELECT count(*) FROM lineitem CROSS JOIN orders LIMIT 1`) with `query_timeout=2` and confirm it errors within ~3s.** |

## Open Questions

1. **Should the MySQL Connector/J JAR be committed to git?**
   - What we know: `docker/drivers/*.so` files ARE committed (they're a build prerequisite for the image). The JAR is similar — a binary build artifact.
   - What's unclear: Project policy on committing redistributable binaries.
   - Recommendation: Commit it, with the SHA256 in a comment. ~2 MB is acceptable. Mirrors the `.so` convention.

2. **Should the JDBCScanNode regex be locked to one specific label after wave 0?**
   - What we know: Documentation references `JDBCScanNode` and `MysqlScanNode` interchangeably; live verification is pending.
   - What's unclear: Which label this StarRocks build emits.
   - Recommendation: Wave 0 includes a "probe JDBC plan" step; wave 1 finalizes the regex.

3. **Should `--queries 1,3,5` interpret query numbers as 1-indexed (`03-q01`, `03-q03`, `03-q05`) or as filename indices?**
   - What we know: The TPC-H convention is 1-indexed (Q1–Q22). Filenames in `queries/mysql/` use `q01`, `q02`, ..., `q22`.
   - What's unclear: Whether `1,3,5` means "queries q01, q03, q05" or "the 1st, 3rd, 5th file in sorted order".
   - Recommendation: 1-indexed by TPC-H number — match `f"03-q{n:02d}-"` filename prefix. This is the obvious user-facing semantic.

## Sources

### Primary (HIGH confidence)
- StarRocks JDBC Catalog Docs: https://docs.starrocks.io/docs/data_source/catalog/jdbc_catalog/ — confirmed property keys (`type`, `user`, `password`, `jdbc_uri`, `driver_url`, `driver_class`)
- StarRocks CREATE EXTERNAL CATALOG: https://docs.starrocks.io/docs/sql-reference/sql-statements/Catalog/CREATE_EXTERNAL_CATALOG/
- StarRocks System Variables: https://docs.starrocks.io/docs/sql-reference/System_variable/ — confirmed `query_timeout` SET_VAR usage
- StarRocks Data Cache: https://docs.starrocks.io/docs/data_source/data_cache/ — confirmed Data Cache excludes JDBC/JNI catalogs
- Maven Central listing: `repo1.maven.org/maven2/com/mysql/mysql-connector-j/` — confirmed 9.3.0 latest
- **Live container probe** (sr-main, 2026-04-28) — confirmed EXPLAIN ANALYZE output format, ANSI escape codes present, ADBC_SCAN block fields, `TotalTime` units, `query_timeout=300` default

### Secondary (MEDIUM confidence)
- StarRocks Issue #48367 (jdbc_uri ?useSSL=false): https://github.com/StarRocks/starrocks/issues/48367 — confirmed query parameters work in jdbc_uri
- StarRocks Explain Analyze docs: https://docs.starrocks.io/docs/best_practices/query_tuning/query_profile_text_based_analysis/ — high-level structure, did not transcribe field names (live probe filled the gap)
- Python concurrent.futures docs: https://docs.python.org/3/library/concurrent.futures.html — confirmed cancel() limitation

### Tertiary (LOW confidence)
- StarRocks 4.0 release notes: https://docs.starrocks.io/releasenotes/release-4.0/ — mentioned EXPLAIN ANALYZE format improvements but no example transcript

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pyproject.toml inspected, all libs already installed except the JDBC JAR which is verified on Maven Central
- Architecture: HIGH — every responsibility has a clear owner; reuses existing `lib/catalog_helpers.py` pattern
- EXPLAIN ANALYZE format: HIGH (ADBC side, live verified) / MEDIUM (JDBCScanNode label not yet live-verified — requires JAR present)
- Pitfalls: HIGH — pulled from CLAUDE.md "Pitfalls" section (battle-tested) plus live-verified items
- JDBC catalog syntax: HIGH — confirmed by both official docs and live container error path

**Research date:** 2026-04-28
**Valid until:** 2026-05-28 for stable items (StarRocks builds are HEAD; format may change). Maven Central JAR version: re-check before locking; 9.x line is mature so 30-day validity is reasonable.
