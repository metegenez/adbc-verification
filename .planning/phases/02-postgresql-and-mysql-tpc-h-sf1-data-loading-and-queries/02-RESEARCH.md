# Phase 2 Research: TPC-H SF1 Data Generation, Loading, and Queries

**Researched:** 2026-04-27

## 1. TPC-H SF1 Data Generation

### Options Evaluated

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **A. Official dbgen (C)** | Spec-compliant, generates exact TPC-H distribution | Requires C compiler; `.tbl` format needs conversion; adds build dependency | Rejected — adds Docker C compilation step |
| **B. Python pure implementation** | No external deps; reproducible seed; runs anywhere; CSV output directly | Must match TPC-H distribution semantics; ~500 lines of code | **Chosen** — self-contained, reproducible |
| **C. tpch-kit (CMake)** | Spec-compliant; used by many benchmarks | Heavy dependency chain; CMake + C++ build | Rejected — overkill for single-SF verification |
| **D. Pre-generated CSV commit** | Zero generation at runtime; fastest startup | 1GB+ files in repo; bloats git clone | Rejected — unnecessary for a CI tool that regenerates each build |

### Chosen: Python Pure Implementation

**Why:** The project already uses Python for data generation (`docker/generate-data.py` for SQLite/DuckDB). A Python SF1 generator follows the same pattern. No C compiler, no dbgen binary, no format conversion. The generator runs once during Docker Compose build (early stage in Dockerfile, or standalone before `docker compose up`).

**TPC-H Data Distribution (SF1):** The generator needs to produce statistically plausible data with proper distributions. Key patterns:
- `p_name`: Formed from adjective list + noun list + "spring/summer/fall/winter" variants
- `p_size`: 1-50 integer range
- `p_type`: Combination of size category + material + finish
- `p_container`: Fixed set of container types
- Keys: Sequential INTEGER PRIMARY KEY (no gaps)
- Foreign keys: Random from valid key ranges
- `l_quantity`: 1-50 uniform
- `l_extendedprice` = `l_quantity * p_retailprice` (from partsupp join)
- `l_discount`: 0.00-0.10 range
- `l_tax`: 0.00-0.08 range
- `l_returnflag`: Weighted distribution (R: 0.25, A: 0.05, N: 0.70)
- `l_linestatus`: 'F' or 'O' (0.49/0.51)
- `o_orderstatus`: 'F', 'O', 'P' with varying distributions
- Date fields: Generated within a 7-year window (1992-01-01 to 1998-12-31)
- `o_totalprice`: Sum of corresponding lineitem extended prices + tax

**Validation approach:** For verification purposes, we don't need exact TPC-H spec compliance (that matters for benchmarking). We need:
1. Correct table schemas (already have these)
2. Correct row counts per SF1 spec
3. Semantically valid cross-table joins (FK relationships work)
4. Deterministic, reproducible output (fixed seed)

**Row counts per SF1:**
| Table | Rows |
|-------|------|
| region | 5 |
| nation | 25 |
| supplier | 10,000 |
| part | 200,000 |
| partsupp | 800,000 |
| customer | 150,000 |
| orders | 1,500,000 |
| lineitem | 6,000,121 |

### Implementation Plan
- `docker/generate-sf1-data.py`: Standalone script, uses `csv` + `random` module with fixed seed
- Generates CSV files to `docker/data/sf1/` directory
- Output: `region.csv`, `nation.csv`, `supplier.csv`, `part.csv`, `partsupp.csv`, `customer.csv`, `orders.csv`, `lineitem.csv`
- Gzip each CSV to reduce volume size (expected: ~200MB compressed vs ~1GB uncompressed)

## 2. Data Loading Strategy

### Options Evaluated

| Approach | PostgreSQL | MySQL | Verdict |
|----------|-----------|-------|---------|
| **A. SQL INSERT files** | Too slow for 8M rows (minutes→hours) | Too slow for 8M rows | Rejected |
| **B. COPY / LOAD DATA** | Native, 100-500K rows/sec | Native, 500K-1M rows/sec | **Chosen** |
| **C. pg_restore / mysqldump** | Requires pre-built dump; non-deterministic | Requires pre-built dump | Rejected — not reproducible |
| **D. Volume-mounted database dir** | Bakes data into image; no init needed | Bakes data; image-per-db | Rejected — large images, brittle |

### Chosen: COPY (PostgreSQL) + LOAD DATA INFILE (MySQL)

**PostgreSQL:** Use `\COPY` in init scripts. Pattern:
```sql
TRUNCATE region CASCADE;
\COPY region FROM '/docker-entrypoint-initdb.d/../../data/sf1/region.csv' WITH (FORMAT csv, HEADER true);
```
- `CASCADE` on TRUNCATE handles FK dependencies
- Loads parent tables first (region, nation, part, supplier, customer), then child tables (partsupp, orders, lineitem)
- Init scripts are mounted at `/docker-entrypoint-initdb.d/` so they execute on first start
- CSV files mounted at `/docker-entrypoint-initdb.d/../../data/sf1/` or a dedicated volume

**MySQL:** Use `LOAD DATA INFILE`. Pattern:
```sql
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE region;
LOAD DATA INFILE '/var/lib/mysql-files/region.csv'
INTO TABLE region
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
SET FOREIGN_KEY_CHECKS = 1;
```
- MySQL's `LOAD DATA INFILE` reads from server-side path; CSV files must be in MySQL container
- Mount CSV files into MySQL container (additional volume mount in docker-compose.yml)
- Disable FK checks during load for speed, re-enable after

**Volume mount:** Add SF1 CSV volume mount to both services:
```yaml
sr-postgres:
  volumes:
    - ./data/sf1/:/sf1-data/:ro
sr-mysql:
  volumes:
    - ./data/sf1/:/sf1-data/:ro
```

## 3. TPC-H Query Adaptation for StarRocks ADBC

### Key SQL Differences

StarRocks SQL through ADBC passthrough has constraints vs native PostgreSQL/MySQL:

| TPC-H Feature | StarRocks Behavior | Adaptation |
|--------------|-------------------|------------|
| `DATE` literals | Must use `'YYYY-MM-DD'` format | Standard — no change needed |
| `EXTRACT(YEAR FROM date)` | Supported | Standard |
| `INTERVAL` arithmetic | `DATEADD()` instead of `+ INTERVAL '3' MONTH` | Replace |
| Subquery in `IN` clause | Must be decorrelated or use `SEMI JOIN` | Use `LEFT SEMI JOIN` where needed |
| `NOT EXISTS` | May need rewriting to `LEFT ANTI JOIN` | Rewrite if StarRocks optimizer fails |
| `LIMIT` in subquery | StarRocks requires LIMIT in subqueries for decorrelation | Add LIMIT |
| `CASE WHEN` | Fully supported | Standard |
| `GROUP BY` aggregate | Standard SQL-92 | Standard |
| `ORDER BY` in subquery | May be unsupported without LIMIT | Add LIMIT |
| `||` string concat | Use `CONCAT()` function | Replace |
| Decimal `*` double | Result is DOUBLE (lossy for large decimals) | Acceptable for verification |

### Query File Convention
Each query file follows the existing pattern:
```sql
-- TPC-H Q01: Pricing Summary Report
-- Catalog: sr_postgres, Schema: public
-- Expected: 4 rows
SELECT
    l_returnflag,
    l_linestatus,
    SUM(l_quantity) AS sum_qty,
    SUM(l_extendedprice) AS sum_base_price,
    SUM(l_extendedprice * (1 - l_discount)) AS sum_disc_price,
    SUM(l_extendedprice * (1 - l_discount) * (1 + l_tax)) AS sum_charge,
    AVG(l_quantity) AS avg_qty,
    AVG(l_extendedprice) AS avg_price,
    AVG(l_discount) AS avg_disc,
    COUNT(*) AS count_order
FROM sr_postgres.public.lineitem
WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL '90' DAY
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus;
```

## 4. Init Script Restructuring

Current state:
```
docker/init/postgres/01-schema.sql  # CREATE TABLE IF NOT EXISTS
docker/init/postgres/02-data.sql    # INSERT seed data (5 rows/table)
```

New structure:
```
docker/init/postgres/01-schema.sql  # CREATE TABLE IF NOT EXISTS (unchanged)
docker/init/postgres/02-data.sql    # TRUNCATE + COPY SF1 data (rewritten)
```

The `02-data.sql` must handle:
1. Drop FK constraints to allow TRUNCATE with CASCADE
2. Load parent tables first, then child tables
3. Re-enable FK constraints
4. Be idempotent (can run on restarted container with existing data)

## 5. Expected Row Counts for TPC-H Queries

The 22 TPC-H queries produce deterministic row counts at SF1 (assuming our data generator is reasonable). These will be validated by hand-running each query against the SF1 data and recording row counts. The `-- Expected: N rows` annotation in each .sql file will be filled with these observed counts.

## 6. Summary of Changes

| Component | Action | Impact |
|-----------|--------|--------|
| `docker/generate-sf1-data.py` | **New** — Python SF1 data generator | Generates 8 CSV files |
| `docker/data/sf1/*.csv.gz` | **New** — Generated SF1 CSV files | Input for init scripts |
| `docker/docker-compose.yml` | **Edit** — Add SF1 data volume | Mount CSVs into backends |
| `docker/init/postgres/02-data.sql` | **Rewrite** — TRUNCATE + COPY | SF1 bulk load |
| `docker/init/mysql/02-data.sql` | **Rewrite** — TRUNCATE + LOAD DATA | SF1 bulk load |
| `queries/postgres/01-q*.sql` | **New** — 22 query files | TPC-H query corpus |
| `queries/mysql/01-q*.sql` | **New** — 22 query files | TPC-H query corpus |
| `queries/postgres/01-select.sql` | **Keep** — Still works with SF1 data | Existing test preserved |
| `queries/postgres/02-join.sql` | **Keep** — Still works with SF1 data | Existing test preserved |
