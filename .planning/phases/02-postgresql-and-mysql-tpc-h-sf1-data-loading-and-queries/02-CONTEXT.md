# Phase 2: PostgreSQL and MySQL TPC-H SF1 Data Loading and Queries — Context

**Gathered:** 2026-04-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Upgrade the PostgreSQL and MySQL backends in the Docker Compose verification suite from TPC-H seed data (5 rows/table) to full TPC-H Scale Factor 1 (~1GB, realistic row counts). Define and execute all 22 TPC-H benchmark queries through the StarRocks ADBC catalog layer, verifying correct results against both backends. Cover row counts, column types, and meaningful query output validation across all 8 TPC-H tables.

**In scope:** PostgreSQL and MySQL only. FlightSQL/SQLite, DuckDB, and SQLite backends are excluded — they are file-based and covered by Phase 1's seed data + existing tests.

**Out of scope:** Other backends, performance benchmarking (wall-clock timing), CSV export/re-import tooling, TPC-H beyond SF1.

This phase delivers a single plan: SF1 data generation + loading + 22 TPC-H queries for both backends.
</domain>

<decisions>
## Implementation Decisions

### Data Generation
- **D-01:** Use Python-based TPC-H data generation (e.g., `sqlglot`-based or custom generator script in `docker/generate-sf1-data.py`). Avoids C-compilation dependency of the official `dbgen` tool. Data is reproducible (fixed seed).
- **D-02:** Output format: CSV files (one per table). CSV is the universal bulk-load format for both PostgreSQL (COPY) and MySQL (LOAD DATA INFILE).

### Data Loading
- **D-03:** Pre-generate SF1 CSV files into `docker/data/sf1/` directory. Mount as read-only volume into sr-postgres and sr-mysql containers. Load at startup via init scripts.
- **D-04:** Loading strategy: PostgreSQL uses `\COPY` in init scripts (fast, native). MySQL uses `LOAD DATA INFILE` (fast, native). Both handle the ~1GB SF1 data in seconds.
- **D-05:** PostgreSQL `DECIMAL→DOUBLE` cast resolution: PostgreSQL TPC-H decimals are defined as `DECIMAL(15,2)` but StarRocks ADBC may cast to DOUBLE. Queries must account for this. No schema change needed — this is a query-level concern.
- **D-06:** Data loading is idempotent: init scripts use `TRUNCATE` + re-import pattern, so restarting containers re-loads from CSVs without duplicates.

### Query Corpus
- **D-07:** All 22 TPC-H standard queries externalized as `.sql` files in `queries/postgres/` and `queries/mysql/`. Catalog-qualified names (e.g., `sr_postgres.public.lineitem`).
- **D-08:** Each query file includes `-- Expected: N rows` annotation for automated assertion by the existing `test_query_file` test.
- **D-09:** Queries are adapted for StarRocks SQL dialect constraints (e.g., subquery decorrelation, LIMIT in subqueries, date literal format). Not raw TPC-H spec SQL.
- **D-10:** TPC-H query results are approximate: row counts only (not exact column values), since the spec defines implementation-variant results. Row counts provide sufficient correctness verification for ADBC passthrough.

### Integration
- **D-11:** The existing `test_queries.py` test discovery (glob `queries/**/*.sql`) automatically picks up new query files. No test code changes needed.
- **D-12:** Existing 35 tests continue to pass — TPC-H seed data tables are replaced by SF1 tables with same schema, so `SELECT * FROM table` still works and returns more rows. `SHOW TABLES` and lifecycle tests are unchanged.

### Agent's Discretion
- Exact Python data generation library (sqlglot, custom Faker-based, or TPC-H kit Python port)
- CSV format details (quoting, escaping, NULL markers)
- Init script structure (single script or per-table scripts)
- Query adaptation specifics for StarRocks SQL dialect
- Exact expected row counts for each query (derived from SF1 spec)
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Foundation
- `.planning/PROJECT.md` — Docker Compose approach, Key Decisions
- `.planning/REQUIREMENTS.md` — v1/v2 requirements, out of scope
- `.planning/ROADMAP.md` — Phase 2 depends on Phase 1

### Phase 1 Output (Phase 2 builds on this)
- `docker/docker-compose.yml` — sr-postgres, sr-mysql services with init script volumes
- `docker/init/postgres/` — 01-schema.sql (8 TPC-H tables), 02-data.sql (seed data)
- `docker/init/mysql/` — 01-schema.sql (8 TPC-H tables), 02-data.sql (seed data)
- `docker/generate-data.py` — Pattern for data generation (SQLite/DuckDB pre-baking)
- `queries/postgres/` — 01-select.sql, 02-join.sql (existing, to be expanded)
- `queries/mysql/` — 01-select.sql, 02-join.sql (existing, to be expanded)
- `tests/test_queries.py` — Auto-discovers .sql files, executes, asserts row counts
- `conftest.py` — Session fixtures for sr_conn, driver paths, Docker Compose lifecyle

### Reference Data
- TPC-H specification v3.0.1 — 8 tables, 22 queries, SF1 row counts
- SF1 expected row counts: region (5), nation (25), supplier (10K), part (200K), partsupp (800K), customer (150K), orders (1.5M), lineitem (6M)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/test_queries.py`: Automatically discovers and executes all .sql files. No changes needed — adding new query files is sufficient.
- `conftest.py`: Session-scoped PostgreSQL and MySQL catalog fixtures already exist (`sr_postgres_cat`, `sr_mysql_cat`). No changes needed.
- `docker/docker-compose.yml`: sr-postgres and sr-mysql services with init script volume mounts. Add SF1 CSV volume mount.
- `docker/init/postgres/01-schema.sql`: TPC-H schema definitions. Unchanged.
- `docker/init/mysql/01-schema.sql`: TPC-H schema definitions. Unchanged.

### What Changes
| Asset | Change | Reason |
|-------|--------|--------|
| `docker/init/postgres/02-data.sql` | Rewritten for SF1 loading via COPY | SF1 data too large for INSERT; COPY is 100x faster |
| `docker/init/mysql/02-data.sql` | Rewritten for SF1 loading via LOAD DATA | SF1 data too large for INSERT; LOAD DATA is 100x faster |
| `docker/generate-data.py` | Updated to generate SF1 CSVs | New data source |
| `docker/data/sf1/` | New directory with generated CSVs | Storage for SF1 CSV files |
| `queries/postgres/*.sql` | 22 TPC-H query files (expanded from 2) | Query coverage |
| `queries/mysql/*.sql` | 22 TPC-H query files (expanded from 2) | Query coverage |

### What Stays the Same
- StarRocks Dockerfile and entrypoint
- Docker Compose service definitions (just add volume mount)
- All existing tests (35 tests from Phase 1)
- `run-verify.py` CLI runner
- `lib/catalog_helpers.py` catalog lifecycle helpers
</code_context>

<specifics>
## Specific Ideas

- Data generator should use fixed seed (e.g., `random.seed(42)`) for reproducible SF1 data across runs
- CSV files should be gzip-compressed to reduce Docker build context size and volume mount overhead
- Init scripts should handle gzipped CSV input (PostgreSQL: `\COPY FROM PROGRAM 'gunzip'`, MySQL: pipe through gunzip or use uncompressed CSVs)
- For PostgreSQL DECIMAL precision: TPC-H query results from StarRocks may show slight floating-point differences vs native PostgreSQL execution. Row counts are the primary correctness signal.
- Existing seed data tables (`test_data`, `departments`) are preserved — only TPC-H tables get SF1 data
</specifics>

<deferred>
## Deferred Ideas

- TPC-H SF10 or higher scale factors — out of scope for Phase 2 (SF1 is 1GB, sufficient for correctness)
- DuckDB, SQLite, FlightSQL TPC-H SF1 — file-based backends have different loading patterns; separate phase
- Performance timing of TPC-H queries — out of scope (Docker wall-clock is noisy)
- Result comparison against reference TPC-H output — row counts are sufficient for this phase
- CSV export tool for debugging — not needed; users can run queries directly
</deferred>

---

*Phase: 02-postgresql-and-mysql-tpc-h-sf1-data-loading-and-queries*
*Context gathered: 2026-04-27*
