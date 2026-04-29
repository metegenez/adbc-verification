# Phase 4: FlightSQL TPC-H Queries Against External StarRocks with Arrow Flight Ports — Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 9 (2 modified Compose/runner, 1 modified test loader, 1 modified requirements doc, 1 new test, 9 new init SQL files, 22 new query SQL files; `lib/catalog_helpers.py` confirmed reuse)
**Analogs found:** 9 / 9

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `docker/docker-compose.yml` (modify — add `sr-external` service) | compose service | request-response | `sr-mysql` block (lines 46-63) for healthcheck shape + bind-mount; `sr-main` block (lines 1-25) for `build: .` + drivers + Compose layout | exact (split between two analogs) |
| `docker/init/sr-external/01-schema.sql` (new) | init SQL (schema DDL) | batch / file-I/O | `docker/init/mysql/01-schema.sql`; `docker/init/postgres/01-schema.sql` | role-match (same TPC-H column shape, different DDL dialect) |
| `docker/init/sr-external/02-region.sql` … `09-lineitem.sql` (new × 8) | init SQL (data load) | batch / file-I/O | `docker/init/mysql/02-data.sql` (TRUNCATE+bulk-load loop); `docker/init/postgres/02-data.sql` (`\COPY` per file) | role-match (same idiom: TRUNCATE + bulk-load CSV per table) |
| `queries/flightsql-starrocks/03-q01..q22.sql` (new × 22) | query SQL | request-response | `queries/mysql/03-q01-pricing-summary.sql` … `03-q22-global-sales-opportunity.sql` | exact (catalog/schema rename only; expected counts identical) |
| `tests/test_flightsql_starrocks.py` (new) | pytest test module | request-response | `tests/test_flightsql.py` (4 of 5 scenarios; TLS dropped) | exact |
| `tests/test_queries.py` (modify — extend `CATALOG_MAP` and add `sr_flightsql_starrocks_cat` fixture) | pytest test module | request-response | existing `CATALOG_MAP` entries + `sr_flightsql_cat` fixture in same file | exact (in-file clone) |
| `conftest.py` (no change required — verified) | pytest fixtures | request-response | `flightsql_driver_path` fixture (lines 96-98), `sr_conn` fixture (lines 73-84) — both reused as-is | exact (no clone needed) |
| `run-verify.py` (modify — add `'sr-external': False` to `_wait_for_healthy()` services dict) | runner / orchestration | event-driven | `_wait_for_healthy()` services dict (lines 183-189) | exact (1-line addition) |
| `.planning/REQUIREMENTS.md` (modify — append FS-SR-01..NN block) | requirements doc | n/a | existing `### Multi-Driver Validation` block (lines 41-56) + `## Traceability` table (lines 89-109) | exact |

---

## Pattern Assignments

### `docker/docker-compose.yml` — add `sr-external` service (compose service, request-response)

**Analog A — `sr-main` block (lines 1-25) for `build: .`, certs mount, sr-net network, healthcheck shape:**

```yaml
services:
  sr-main:
    build: .
    container_name: sr-main
    ports:
      - "9030:9030"
    volumes:
      - ./certs/:/opt/starrocks/certs/:ro
    networks:
      - sr-net
    depends_on:
      sr-postgres:
        condition: service_healthy
      sr-mysql:
        condition: service_healthy
      sr-flightsql:
        condition: service_started
      sr-flightsql-tls:
        condition: service_started
    healthcheck:
      test: ["CMD", "mysql", "-uroot", "-h127.0.0.1", "-P9030", "-e", "SELECT 1"]
      interval: 5s
      timeout: 3s
      retries: 60
      start_period: 60s
```

**Analog B — `sr-mysql` block (lines 46-63) for SF1 bind-mount + larger `start_period`:**

```yaml
  sr-mysql:
    image: mysql:8.0
    container_name: sr-mysql
    command: ["--max-connections=500"]
    environment:
      MYSQL_ROOT_PASSWORD: testpass
      MYSQL_DATABASE: testdb
    volumes:
      - ./init/mysql/:/docker-entrypoint-initdb.d/:ro
      - ./data/sf1/:/var/lib/mysql-files/
    networks:
      - sr-net
    healthcheck:
      test: ["CMD", "mysql", "-h", "127.0.0.1", "--protocol=TCP", "-uroot", "-ptestpass", "-e", "SELECT 1"]
      interval: 5s
      timeout: 3s
      retries: 60
      start_period: 300s
```

**Clone:** Take `sr-main`'s `build: .` + sr-net + healthcheck command (`mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"`); add `sr-mysql`'s init bind-mount pattern (`./init/<role>/:/docker-entrypoint-initdb.d/:ro`) and SF1 mount (but `:ro` — research D-06 + Pitfall on chown trap not applicable to StarRocks). Drop `ports:` (Compose-internal only per D-02). Add `start_period: 180s` (research-verified empirically). Also add `sr-external: { condition: service_healthy }` to `sr-main.depends_on` (insert into the existing `depends_on` block at lines 11-19).

---

### `docker/init/sr-external/01-schema.sql` (new — init SQL, batch DDL)

**Analog: `docker/init/mysql/01-schema.sql` (lines 1-89):**

```sql
-- MySQL init: schema (idempotent via IF NOT EXISTS)
-- Backend service: sr-mysql (mysql:8.0, user=root, db=testdb)

CREATE TABLE IF NOT EXISTS region (
    r_regionkey INT PRIMARY KEY,
    r_name VARCHAR(25) NOT NULL,
    r_comment VARCHAR(152)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS nation (
    n_nationkey INT PRIMARY KEY,
    n_name VARCHAR(25) NOT NULL,
    n_regionkey INT NOT NULL,
    n_comment VARCHAR(152)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS lineitem (
    l_orderkey INT NOT NULL,
    l_partkey INT NOT NULL,
    l_suppkey INT NOT NULL,
    l_linenumber INT NOT NULL,
    l_quantity DECIMAL(15,2) NOT NULL,
    l_extendedprice DECIMAL(15,2) NOT NULL,
    l_discount DECIMAL(15,2) NOT NULL,
    l_tax DECIMAL(15,2) NOT NULL,
    l_returnflag CHAR(1) NOT NULL,
    l_linestatus CHAR(1) NOT NULL,
    l_shipdate DATE NOT NULL,
    l_commitdate DATE NOT NULL,
    l_receiptdate DATE NOT NULL,
    l_shipinstruct VARCHAR(25) NOT NULL,
    l_shipmode VARCHAR(10) NOT NULL,
    l_comment VARCHAR(44) NOT NULL,
    PRIMARY KEY (l_orderkey, l_linenumber)
) ENGINE=InnoDB;
```

**Clone:** Same column names/types/lengths (DECIMAL(15,2), CHAR(1), DATE, VARCHAR(N) all map directly to StarRocks). **Change:**
1. Prepend `CREATE DATABASE IF NOT EXISTS tpch;` and `USE tpch;` (StarRocks needs explicit DB; mysql gets one from `MYSQL_DATABASE: testdb` env).
2. Drop `ENGINE=InnoDB`. Drop `PRIMARY KEY` clauses (StarRocks "key columns must be ordered prefix" pitfall — research Pitfall 1; use auto-pick).
3. Append `DISTRIBUTED BY HASH(<first_col>) PROPERTIES('replication_num' = '1')` per CREATE TABLE (single-BE deployment).
4. Use `INT NOT NULL` (or just `INT`) — research Example 2 has the full verified DDL for all 8 tables.

---

### `docker/init/sr-external/02-region.sql` … `09-lineitem.sql` (new × 8 — init SQL, batch file-I/O)

**Analog A — `docker/init/mysql/02-data.sql` (lines 11-16) for the TRUNCATE+bulk-load idiom:**

```sql
SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE region;
LOAD DATA INFILE '/var/lib/mysql-files/region.csv'
    INTO TABLE region
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE lineitem;
LOAD DATA INFILE '/var/lib/mysql-files/lineitem.csv'
    INTO TABLE lineitem
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;
```

**Analog B — `docker/init/postgres/02-data.sql` (lines 17-24) for the path/options style closer to StarRocks `FILES()`:**

```sql
\COPY region   FROM '/sf1-data/region.csv'   WITH (FORMAT csv, HEADER true);
\COPY nation   FROM '/sf1-data/nation.csv'   WITH (FORMAT csv, HEADER true);
\COPY lineitem FROM '/sf1-data/lineitem.csv' WITH (FORMAT csv, HEADER true);
```

**Clone (one file per table, prefixed `02-`..`09-` to control init order):**
```sql
USE tpch;
TRUNCATE TABLE <table>;     -- StarRocks requires the TABLE keyword (research Pattern 3)
INSERT INTO <table>
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/<table>.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);
```

**Change vs. mysql analog:** path is `file:///opt/starrocks/data/sf1/<table>.csv` (in-container, bind-mounted read-only — D-06 + research Example 1); use StarRocks `FILES()` (research Pattern 1, verified live loading 6M lineitem rows in ~3.7s); skip the FK-check sandwich (StarRocks has no FKs); split the postgres-style monolith into one file per table for clearer init logs (research recommendation in Code Examples / Example 3 footnote).

**Order note:** Alphabetical-by-prefix: `02-region`, `03-nation`, `04-supplier`, `05-part`, `06-partsupp`, `07-customer`, `08-orders`, `09-lineitem`. StarRocks has no FKs so order is cosmetic, but matches the entrypoint `for f in *.sql` glob ordering.

---

### `queries/flightsql-starrocks/03-q01..q22.sql` (new × 22 — query SQL, request-response)

**Analog A — `queries/mysql/03-q01-pricing-summary.sql` (simple aggregation, full file):**

```sql
-- TPC-H Q01: Pricing Summary Report
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 3 rows
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
FROM sr_mysql.testdb.lineitem
WHERE l_shipdate <= DATE_SUB('1998-12-01', INTERVAL 90 DAY)
GROUP BY l_returnflag, l_linestatus
ORDER BY l_returnflag, l_linestatus;
```

**Analog B — `queries/mysql/03-q06-forecasting-revenue-change.sql` (small aggregation w/ DATE_ADD):**

```sql
-- TPC-H Q06: Forecasting Revenue Change
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 1 rows
SELECT
    SUM(l_extendedprice * l_discount) AS revenue
FROM sr_mysql.testdb.lineitem
WHERE l_shipdate >= '1994-01-01'
  AND l_shipdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
  AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01
  AND l_quantity < 24;
```

**Analog C — `queries/mysql/03-q07-volume-shipping.sql` (multi-table join):**

```sql
-- TPC-H Q07: Volume Shipping
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 4 rows
SELECT
    supp_nation,
    cust_nation,
    l_year,
    SUM(volume) AS revenue
FROM (
    SELECT
        n1.n_name AS supp_nation,
        n2.n_name AS cust_nation,
        YEAR(l_shipdate) AS l_year,
        l_extendedprice * (1 - l_discount) AS volume
    FROM sr_mysql.testdb.supplier
    JOIN sr_mysql.testdb.lineitem ON s_suppkey = l_suppkey
    JOIN sr_mysql.testdb.orders   ON o_orderkey = l_orderkey
    JOIN sr_mysql.testdb.customer ON c_custkey = o_custkey
    JOIN sr_mysql.testdb.nation n1 ON s_nationkey = n1.n_nationkey
    JOIN sr_mysql.testdb.nation n2 ON c_nationkey = n2.n_nationkey
    WHERE (
        (n1.n_name = 'FRANCE' AND n2.n_name = 'GERMANY')
        OR (n1.n_name = 'GERMANY' AND n2.n_name = 'FRANCE')
    )
    AND l_shipdate BETWEEN '1995-01-01' AND '1996-12-31'
) shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year;
```

**Clone:** Verbatim. **Change in every file:**
1. Header comment: `-- Catalog: sr_mysql, Schema: testdb` → `-- Catalog: sr_flightsql_starrocks, Schema: tpch`
2. Every fully-qualified table reference: `sr_mysql.testdb.<table>` → `sr_flightsql_starrocks.tpch.<table>`
3. Keep `-- Expected: N rows` value identical (research Pitfall 6: mysql counts apply because SF1 CSVs are byte-identical; verified live for Q01=3, Q06=1, Q22=0).
4. Do NOT carry over any `-- Skip:` directives — none in mysql versions; postgres-numeric Arrow gap does not apply to StarRocks-native DECIMAL.

**Why mysql, not postgres:** The 17 postgres queries are skipped via `-- Skip:` due to the postgres-numeric Arrow opaque type. mysql versions all pass and have empirically-verified expected counts.

---

### `tests/test_flightsql_starrocks.py` (new — pytest test module, request-response)

**Analog: `tests/test_flightsql.py` (full file). Concrete excerpts to clone verbatim, then rewrite:**

**Imports + module docstring (lines 1-18 of analog):**
```python
"""FlightSQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data query, negative, pass-through) and D-11
(TLS with self-signed certs). Uses the sr-flightsql and sr-flightsql-tls Docker
Compose services.
"""

from __future__ import annotations

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)
```

**Lifecycle test (analog lines 22-51) — copy verbatim, then change URI + auth + add `tpch` assertion:**
```python
@pytest.mark.flightsql
def test_flightsql_catalog_lifecycle(sr_conn, flightsql_driver_path, sqlflite_port):
    """CREATE / SHOW / SHOW DATABASES / DROP cycle on a non-TLS FlightSQL catalog."""
    cat = "test_fs_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri="grpc://sr-flightsql:31337",
            extra_props={
                "username": "sqlflite_username",
                "password": "sqlflite_password",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not found in {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {dbs}"

    finally:
        drop_catalog(sr_conn, cat)

    catalogs = show_catalogs(sr_conn)
    assert cat not in catalogs, f"{cat} still present after DROP"
```

**Wrong-password test (analog lines 147-172) — copy verbatim, then change URI + auth:**
```python
@pytest.mark.flightsql
def test_flightsql_wrong_password(sr_conn, flightsql_driver_path, sqlflite_port):
    """Wrong password must cause an error at catalog creation or query time."""
    cat = "test_fs_wp"
    create_succeeded = False
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=flightsql_driver_path,
                uri="grpc://sr-flightsql:31337",
                extra_props={
                    "username": "sqlflite_username",
                    "password": "wrong_password",
                },
            )
            create_succeeded = True
        except pymysql.err.DatabaseError:
            return

        with pytest.raises(pymysql.err.DatabaseError):
            execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")

    finally:
        drop_catalog(sr_conn, cat)
```

**Clone (4 tests; TLS scenario lines 102-140 INTENTIONALLY OMITTED per D-14):**
For every test in the new file:
1. Replace `uri="grpc://sr-flightsql:31337"` → `uri="grpc://sr-external:9408"` (D-16; research-verified live).
2. Replace `extra_props={"username": "sqlflite_username", "password": "sqlflite_password"}` → `{"username": "root", "password": ""}` (D-13).
3. Drop the `sqlflite_port` fixture parameter (no port lookup needed for sr-external; URI is hard-coded).
4. Rename test functions to `test_flightsql_sr_*` per D-15.
5. In `test_flightsql_sr_data_query`: assert `'tpch' in db_names` and `len(SELECT * FROM cat.tpch.region) == 5` (research Example 4 has the verified shape).
6. Add `drop_catalog(sr_conn, cat)` BEFORE the `try:` in each test (defensive cleanup — research Example 4 includes this; existing analog only does it inside `test_flightsql_tls_lifecycle`).

The full canonical 4-test skeleton already exists verbatim in `04-RESEARCH.md` Example 4 (lines 677-824). Reference that.

---

### `tests/test_queries.py` — modify `CATALOG_MAP` and add session fixture (test loader, request-response)

**Existing `CATALOG_MAP` (lines 19-28) — show in full so the planner can drop in the new entry:**

```python
# Map catalog name → (driver fixture name, URI, entrypoint or None)
CATALOG_MAP: dict[str, tuple[str, str, str | None]] = {
    "sr_sqlite":      ("sqlite_driver_path",    "/opt/starrocks/data/tpch_sqlite.db",     None),
    "sr_sqlite_emp":  ("sqlite_driver_path",    "/opt/starrocks/data/cross_sqlite_a.db",  None),
    "sr_postgres":    ("postgres_driver_path",  "postgresql://testuser:testpass@sr-postgres:5432/testdb", None),
    "sr_mysql":       ("mysql_driver_path",     "mysql://root:testpass@sr-mysql:3306/testdb",       None),
    "sr_flightsql":   ("flightsql_driver_path", "grpc://sr-flightsql:31337",              None),
    # DuckDB: use :memory: for query tests — file-based URI has single-writer lock conflict with FE
    "sr_duckdb":      ("duckdb_driver_path",    ":memory:",                                "duckdb_adbc_init"),
}
```

**Existing `sr_flightsql_cat` fixture (lines 94-105) — clone shape verbatim:**

```python
@pytest.fixture(scope="session")
def sr_flightsql_cat(sr_conn, flightsql_driver_path):
    cat = "sr_flightsql"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path,
                        uri=CATALOG_MAP["sr_flightsql"][1],
                        extra_props={
                            "username": "sqlflite_username",
                            "password": "sqlflite_password",
                        })
    yield cat
    drop_catalog(sr_conn, cat)
```

**Existing `test_query_file` signature (lines 131-134):**

```python
@pytest.mark.parametrize("driver,path", list(_discover_query_files()))
def test_query_file(sr_conn, driver, path,
                    sr_sqlite_cat, sr_sqlite_emp_cat, sr_postgres_cat,
                    sr_mysql_cat, sr_flightsql_cat, sr_duckdb_cat):
```

**Three edits the planner must make:**

1. **Add to `CATALOG_MAP` (after line 25, the `sr_flightsql` entry):**
```python
    "sr_flightsql_starrocks": ("flightsql_driver_path", "grpc://sr-external:9408", None),
```

2. **Add session-scoped fixture (after the existing `sr_flightsql_cat` fixture at line 105) — clone of `sr_flightsql_cat` with StarRocks auth:**
```python
@pytest.fixture(scope="session")
def sr_flightsql_starrocks_cat(sr_conn, flightsql_driver_path):
    cat = "sr_flightsql_starrocks"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path,
                        uri=CATALOG_MAP["sr_flightsql_starrocks"][1],
                        extra_props={
                            "username": "root",
                            "password": "",
                        })
    yield cat
    drop_catalog(sr_conn, cat)
```

3. **Extend `test_query_file` signature to inject the new fixture (line 132-134):**
```python
def test_query_file(sr_conn, driver, path,
                    sr_sqlite_cat, sr_sqlite_emp_cat, sr_postgres_cat,
                    sr_mysql_cat, sr_flightsql_cat, sr_duckdb_cat,
                    sr_flightsql_starrocks_cat):
```

**No driver-skip changes needed:** the `driver` param is the directory name (`flightsql-starrocks`), and lines 144-150 of the existing handler already skip only `duckdb` and `flightsql + join` paths. The new directory is auto-discovered by `_discover_query_files()` (line 123-128) without any change.

---

### `conftest.py` — verified: NO change required

**Existing `flightsql_driver_path` fixture (lines 96-98):**
```python
@pytest.fixture(scope="session")
def flightsql_driver_path() -> str:
    return FLIGHTSQL_DRIVER
```

**Existing `sr_conn` fixture (lines 73-84):**
```python
@pytest.fixture(scope="session")
def sr_conn():
    """Connect to StarRocks FE via STARROCKS_HOST:STARROCKS_PORT."""
    conn = pymysql.connect(
        host=STARROCKS_HOST,
        port=STARROCKS_PORT,
        user="root",
        password="",
        autocommit=True,
    )
    yield conn
    conn.close()
```

**Note:** Both fixtures are reused unchanged. The `FLIGHTSQL_DRIVER` constant at line 30 (`/opt/starrocks/drivers/libadbc_driver_flightsql.so`) is the only path needed; the new `sr_flightsql_starrocks_cat` fixture lives in `tests/test_queries.py` (not conftest), parallel to `sr_flightsql_cat`. Do NOT add a duplicate fixture in `conftest.py` — that would shadow the test-loader fixture and create a fixture-graph collision.

If a future reviewer suggests "promote the new fixture to conftest.py for sharing across test_flightsql_starrocks.py and test_queries.py" — DO NOT. `tests/test_flightsql_starrocks.py` mirrors `tests/test_flightsql.py`, which creates its own ad-hoc catalogs in each test (does not depend on `sr_flightsql_cat`). Same convention for the StarRocks variant.

---

### `run-verify.py` — modify `_wait_for_healthy()` services dict (runner / orchestration, event-driven)

**Existing services dict (lines 181-189):**
```python
def _wait_for_healthy() -> bool:
    deadline = time.monotonic() + HEALTHCHECK_TIMEOUT
    services = {
        "sr-mysql": False,
        "sr-postgres": False,
        "sr-flightsql": False,
        "sr-flightsql-tls": False,
        "sr-main": False,
    }
    reported: set[str] = set()
```

**Clone:** Add one entry. Insert `"sr-external": False,` between `"sr-flightsql-tls": False,` and `"sr-main": False,` (alphabetical-ish + matches the natural `depends_on` ordering — sr-external must be healthy before sr-main per D-04).

**Resulting dict:**
```python
    services = {
        "sr-mysql": False,
        "sr-postgres": False,
        "sr-flightsql": False,
        "sr-flightsql-tls": False,
        "sr-external": False,
        "sr-main": False,
    }
```

**Why required:** Compose's own `depends_on` chain takes care of intra-Compose ordering; but `run-verify.py` does its OWN wait loop before invoking pytest, and the loop returns success the moment all dict-entries flip green. Without `sr-external` in the dict, the runner can launch pytest BEFORE sr-external's SF1 init has finished (research Pitfall 7). Five-line edit; CLAUDE.md "Pitfalls — run-verify.py quirks" calls this out explicitly.

**No other change to `run-verify.py`:** The ready-check at line 217 (`ready = health == "healthy" or (health == "" and state == "running")`) handles healthchecked services correctly (sr-external has a healthcheck; sets `health == "healthy"`). The `start_period: 180s` sized in the compose service (D-04) is well within `HEALTHCHECK_TIMEOUT = 300` at line 29.

---

### `.planning/REQUIREMENTS.md` — append FS-SR-01..FS-SR-NN block (requirements doc)

**Analog A — existing v1 requirements format (lines 41-56):**

```markdown
### Multi-Driver Validation (Existing — Adapted)

These are the inherited test modules from the existing suite. They must pass against the Docker Compose environment after conftest adaptation.

- [x] **VAL-01
**: SQLite catalog lifecycle, data round-trip, error paths (6 tests)
- [x] **VAL-02
**: DuckDB catalog lifecycle, data round-trip, entrypoint, pass-through (4 tests)
- [x] **VAL-03
**: MySQL catalog lifecycle, data round-trip, SHOW TABLES, errors, cross-join (5 tests)
- [x] **VAL-04
**: PostgreSQL catalog lifecycle, data round-trip, SHOW TABLES, errors, TLS, passthrough (6 tests)
- [x] **VAL-05
**: FlightSQL catalog lifecycle, data round-trip, TLS, auth, passthrough (5 tests)
- [x] **VAL-06
**: Cross-driver JOIN tests across heterogeneous backends (2 tests)
- [x] **VAL-07
**: Negative/validation error path coverage for all PROP/VAL rules (7 tests)
```

**Analog B — existing traceability table (lines 89-109):**

```markdown
| Requirement | Phase | Plan | Status |
|-------------|-------|------|--------|
| DC-01 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| DC-02 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| ...
| VAL-05 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
```

**Note on the format quirk:** Line breaks in the bold IDs are intentional (`**VAL-01\n**:`). Match this exact shape — Markdown renders the same as `**VAL-01**:` but the existing file uses the multi-line form throughout.

**Clone:** Add a new subsection under `## v1 Requirements` (likely after the "TPC-H Depth" section) titled `### FlightSQL → External StarRocks (Phase 4)`, with one bullet per D-XX from CONTEXT.md mapped to a stable FS-SR-NN ID:
```markdown
- [ ] **FS-SR-01
**: External StarRocks (sr-external) Compose service exists with no host ports, builds from same Dockerfile as sr-main (D-01, D-02, D-03)
- [ ] **FS-SR-02
**: sr-external owns native StarRocks TPC-H tables under `tpch` database, populated from SF1 CSVs via `INSERT FROM FILES()` (D-05, D-07, D-08)
- [ ] **FS-SR-03
**: sr-main `depends_on sr-external: { condition: service_healthy }` (D-04)
- [ ] **FS-SR-04
**: ADBC FlightSQL catalog `sr_flightsql_starrocks` connects to `grpc://sr-external:9408` (D-11, D-13, D-16)
- [ ] **FS-SR-05
**: 22 TPC-H queries under `queries/flightsql-starrocks/` execute against sr-external with correct row counts (D-09, D-10)
- [ ] **FS-SR-06
**: Lifecycle / data / wrong-password / passthrough tests pass in `tests/test_flightsql_starrocks.py` (D-15)
- [ ] **FS-SR-07
**: Both FlightSQL paths (sqlflite + sr-external) coexist; existing tests untouched (D-12)
```

Then extend the `## Traceability` table at line 91 with rows mapping each FS-SR-NN to `Phase 4: FlightSQL TPC-H ...` and the planner's plan IDs (`04-01`, `04-02`, etc., to be assigned). Update the coverage tally at line 111 (`v1 requirements: 17 total` → bump by NN).

---

### `lib/catalog_helpers.py` — verified: NO change required

**Existing `create_adbc_catalog()` signature (lines 6-13):**

```python
def create_adbc_catalog(
    conn,
    catalog_name: str,
    driver_url: str,
    uri: str = "",
    extra_props: dict | None = None,
    entrypoint: str = "",
) -> None:
```

**Confirmation:** The function emits `CREATE EXTERNAL CATALOG <name> PROPERTIES("type"="adbc", "driver_url"="...", "uri"="...", <extra_props as kv pairs>)`. The `extra_props` dict accepts arbitrary keys, including `username`, `password`, and `adbc.flight.sql.*` passthrough — the new tests in `test_flightsql_starrocks.py` and the `sr_flightsql_starrocks_cat` fixture both call this directly with the same shape `tests/test_flightsql.py` already uses. **No new helper, no signature change.**

`drop_catalog()` (line 81), `show_catalogs()` (line 87), and `execute_sql()` (line 94) are reused as-is in the new test module.

---

## Shared Patterns

### Catalog lifecycle pattern (try/finally with `drop_catalog`)

**Source:** `tests/test_flightsql.py:26-51` (every test in the file).
**Apply to:** Every test in the new `tests/test_flightsql_starrocks.py`.

```python
@pytest.mark.flightsql
def test_xxx(sr_conn, flightsql_driver_path):
    cat = "test_fs_sr_xxx"
    drop_catalog(sr_conn, cat)   # defensive pre-clean (idiom from research Example 4)
    try:
        create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path, ...)
        # assertions
    finally:
        drop_catalog(sr_conn, cat)
```

**Rationale:** CLAUDE.md "Key Rules" — tests must not leave catalogs behind. The defensive `drop_catalog` BEFORE `try:` (per research Example 4) protects against a previous run leaking state. Already used by `test_flightsql_tls_lifecycle` at line 108 of the analog.

---

### Compose service shape (StarRocks-flavored)

**Source:** `docker/docker-compose.yml:1-25` (sr-main).
**Apply to:** Any new StarRocks-image-based service.

Required keys: `build: .`, `container_name`, `volumes` (with at minimum `./certs/:/opt/starrocks/certs/:ro` for parity), `networks: [sr-net]`, `healthcheck` with the exact command `["CMD", "mysql", "-uroot", "-h127.0.0.1", "-P9030", "-e", "SELECT 1"]` (CLAUDE.md "Pitfalls — MySQL healthcheck" — TCP, not socket; same shape applies here because StarRocks FE speaks MySQL protocol). `interval: 5s`, `timeout: 3s`, `retries: 60` are the project standard.

`start_period` is service-specific:
- 60s for sr-main (no init data)
- 300s for sr-postgres / sr-mysql (large `LOAD DATA` / `\COPY`)
- 180s for sr-external (research-recommended; FE+BE warmup ~60s + SF1 `FILES()` load ~30s + buffer)

---

### TPC-H query file shape

**Source:** All 22 files in `queries/mysql/03-q*.sql`.
**Apply to:** All 22 files in `queries/flightsql-starrocks/03-q*.sql`.

Header line 1: `-- TPC-H Q<N>: <human title>`
Header line 2: `-- Catalog: <catalog>, Schema: <schema>`
Header line 3: `-- Expected: <N> rows`
Body: standard TPC-H Q01-Q22 with all table refs as `<catalog>.<schema>.<table>`.

The `tests/test_queries.py` parser reads lines 1-3 (`_strip_comments`, `_expected_rows`, `_skip_reason` at lines 31-46 of the loader) — adhering to this shape is mechanical.

---

## No Analog Found

| File | Role | Reason |
|---|---|---|
| (none) | — | Every new file in this phase has at least one strong analog already in the codebase. |

---

## Metadata

**Analog search scope:**
- `docker/docker-compose.yml`
- `docker/init/{postgres,mysql,sqlflite}/`
- `docker/Dockerfile`, `docker/entrypoint.sh`
- `queries/{mysql,postgres,sqlite,duckdb,flightsql,cross-join}/`
- `tests/test_*.py`
- `lib/catalog_helpers.py`
- `conftest.py`
- `run-verify.py`
- `.planning/REQUIREMENTS.md`

**Files scanned:** 21 (all read once, no re-reads — file ranges are non-overlapping).

**Pattern extraction date:** 2026-04-29

**Research cross-references:** Where this PATTERNS.md cites a "research-verified" or "research Example N" claim, see `04-RESEARCH.md` lines 286-365 (Patterns 1-3), 519-654 (Examples 1-3 — compose service, schema, data load), 677-824 (Example 4 — full test skeleton), 826-849 (Example 5 — query file format), 851-882 (Example 6 — test_queries.py fixture wiring).
