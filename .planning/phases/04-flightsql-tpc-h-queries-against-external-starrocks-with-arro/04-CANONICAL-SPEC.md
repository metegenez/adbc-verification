# Phase 4: Canonical TPC-H Format Spec

**Status:** Contract for plans 04-02 and 04-05.
**Purpose:** Single source of truth for the canonical-query format that the data generator (04-05) produces and the test loader (04-02) consumes.

## File location

- Canonical home: `queries/tpch/q01.sql` … `q22.sql` (22 files)
- DELETED: `queries/mysql/03-q01-*.sql` … `queries/mysql/03-q22-*.sql` (22 files)
- DELETED: `queries/postgres/03-q01-*.sql` … `queries/postgres/03-q22-*.sql` (22 files)
- KEPT untouched: `queries/mysql/01-select.sql`, `02-join.sql`; `queries/postgres/01-select.sql`, `02-join.sql`; `queries/sqlite/`, `queries/duckdb/`, `queries/flightsql/`, `queries/cross-join/`
- Naming: drop the `03-` prefix and the `-<title-slug>` suffix in the canonical home (just `q01.sql` … `q22.sql`). Rationale: `03-` was a Phase 3 numbering artifact; canonical queries aren't tied to a phase.

## Catalog placeholders

Use template literals replaced at runtime by `tests/test_queries.py`:

```sql
-- TPC-H Q01: Pricing Summary Report
-- Expected (postgres): 4 rows
-- Expected (mysql): 4 rows
-- Expected (flightsql-starrocks): 4 rows
SELECT l_returnflag, l_linestatus, sum(l_quantity), ...
FROM {catalog}.{db}.lineitem
WHERE l_shipdate <= date '1998-12-01' - interval '90' day
GROUP BY l_returnflag, l_linestatus;
```

Substitution happens once per (query × backend) at test collection time.

## Backend → (catalog, db) mapping (in `tests/test_queries.py`)

```python
CANONICAL_BACKENDS = {
    "postgres":             ("sr_postgres",            "public"),
    "mysql":                ("sr_mysql",               "testdb"),
    "flightsql-starrocks":  ("sr_flightsql_starrocks", "tpch"),
}
```

## Per-backend skip manifest (in `tests/test_queries.py`)

Replaces inline `-- Skip:` directives. Keyed by backend, valued by set of canonical query names:

```python
CANONICAL_SKIPS: dict[str, set[str]] = {
    "postgres": {
        "q01", "q02", "q03", "q05", "q06", "q07", "q08", "q09", "q10",
        "q11", "q14", "q15", "q17", "q18", "q19", "q20", "q22",
    },
    # reason for the postgres set: postgres-numeric Arrow extension type unsupported in StarRocks BE
    # see .planning/phases/02-postgresql-and-mysql-tpc-h-sf1-data-loading-and-queries/02-NOTES-postgres-numeric.md
    "mysql": set(),
    "flightsql-starrocks": set(),
}
```

A small constant at the top of `test_queries.py` documents the postgres skip reason. The 17 IDs above are the queries that currently have inline `-- Skip:` in `queries/postgres/03-q*.sql`. Working postgres queries: q04, q12, q13, q16, q21.

## Expected row counts

Canonical TPC-H SF1 (DuckDB-generated) values are inlined per query as:

```sql
-- Expected (postgres): N rows
-- Expected (mysql): N rows
-- Expected (flightsql-starrocks): N rows
```

When all three values are equal (the common case), a single line `-- Expected: N rows` is acceptable.

If they ever diverge (e.g., a backend's grouping semantics differ on edge cases), the per-backend form takes precedence.

## Test loader contract (`tests/test_queries.py` changes)

1. `_skip_reason()` and inline `-- Skip:` parsing — REMOVED. Replaced by `CANONICAL_SKIPS` lookup.
2. New `_load_canonical(query_name, backend)`: reads `queries/tpch/{query_name}.sql`, substitutes `{catalog}.{db}` from `CANONICAL_BACKENDS[backend]`, returns SQL.
3. Existing `_expected_rows()` parser keeps working — extends to recognize `-- Expected (backend): N rows` form.
4. Existing per-backend special skips (DuckDB :memory: has no TPC-H, FlightSQL sqlflite has no orders/lineitem) — migrate to `CANONICAL_SKIPS["duckdb"] = set(...)` etc. These backends don't run canonical TPC-H, so they get all 22 ids skipped.
5. The pytest parametrization changes from "directory glob" to "(canonical_query × backend) cross product" for backends in `CANONICAL_BACKENDS`. Other directories (`queries/sqlite/`, `queries/duckdb/`, `queries/flightsql/`, `queries/cross-join/`, `queries/mysql/01-select.sql`, etc.) keep the existing per-directory mechanism.

## Generator output contract (04-05)

`docker/generate-sf1-data.py` produces 8 CSVs with canonical TPC-H SF1 row counts:

| Table | Rows |
|-------|------|
| region | 5 |
| nation | 25 |
| supplier | 10000 |
| part | 200000 |
| partsupp | 800000 |
| customer | 150000 |
| orders | 1500000 |
| lineitem | 6001215 |

CSVs:
- LF line endings (`\n`), not CRLF — required by MySQL `LOAD DATA INFILE` per CLAUDE.md
- **Header row REQUIRED** — first line is the TPC-H column names (e.g., `r_regionkey,r_name,r_comment`). All existing consumers (postgres `\COPY ... WITH (FORMAT csv, HEADER true)`, mysql `LOAD DATA INFILE ... IGNORE 1 ROWS`, sr-external init `csv.skip_header='1'`) strip the header at load time. Producing headerless CSVs would silently shift every column by one row.
- Comma-separated
- Decimals as plain digits (no thousands separators)
- Dates as `YYYY-MM-DD`
- NULLs not present (TPC-H spec doesn't include NULLs at SF1)

Implementation: DuckDB `tpch` extension via `INSTALL tpch; LOAD tpch; CALL dbgen(sf=1)` followed by `COPY <table> TO '<path>' (FORMAT CSV, HEADER TRUE, DELIMITER ',')`. Verify line endings are LF after COPY.

## Calibration step (04-05 verification)

After regenerating CSVs, the planner must:

1. `docker compose down -v` (clear named volumes — postgres/mysql have stale data)
2. `docker compose up -d` (postgres + mysql + sr-external load canonical CSVs at boot)
3. For each q01..q22, run via the test loader against postgres + mysql + (later in Wave 2) sr-external
4. Record observed row counts
5. Update `-- Expected (backend): N rows` comments in `queries/tpch/q*.sql`

Postgres count for skipped queries: not measurable (skip is at the test level, not at the StarRocks-BE level). The skip prevents a result from being produced. For these queries, only `-- Expected (mysql): N rows` and `-- Expected (flightsql-starrocks): N rows` are recorded.
