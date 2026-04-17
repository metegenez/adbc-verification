# StarRocks ADBC Verification Suite

Integration test suite for the StarRocks ADBC catalog connector. Validates catalog lifecycle, data round-trips, cross-driver joins, error handling, and TLS across multiple ADBC driver backends.

## Prerequisites

- Python 3.11+
- Running StarRocks cluster (FE + BE) built from `feature/adbc-catalog-2`
- Docker (for FlightSQL, MySQL, PostgreSQL backends)
- ADBC drivers installed via `dbc` CLI

### Install drivers

```bash
~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql
```

Driver configs are read from `~/.config/adbc/drivers/<name>.toml`.

### Set up Python environment

```bash
cd adbc_verification
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Usage

```bash
# Set STARROCKS_HOME to your StarRocks build output
export STARROCKS_HOME=/path/to/starrocks

# Run all 35 tests
.venv/bin/pytest tests/ -v --no-header --tb=line

# Run a single module
.venv/bin/pytest tests/test_sqlite.py -v --tb=short

# Run a single test
.venv/bin/pytest tests/test_flightsql.py -k "test_flightsql_tls_lifecycle" -v -s --tb=long
```

## Test Modules

| Module | Tests | Docker | Driver |
|--------|-------|--------|--------|
| `test_sqlite.py` | 6 | None | sqlite |
| `test_duckdb.py` | 4 | None | duckdb |
| `test_mysql.py` | 5 | mysql:8.0 (auto) | mysql |
| `test_postgres.py` | 6 | postgres:16 (auto) | postgresql |
| `test_flightsql.py` | 5 | voltrondata/sqlflite (auto) | flightsql |
| `test_cross_join.py` | 2 | postgres:16 (auto) | sqlite + postgresql |
| `test_negative.py` | 7 | None | sqlite |

Docker containers are started automatically by session-scoped fixtures and torn down after the test session.

## Project Structure

```
adbc_verification/
  conftest.py          # Session fixtures: StarRocks connection, drivers, Docker backends
  pyproject.toml       # Project config and pytest settings
  lib/
    catalog_helpers.py  # CREATE/DROP CATALOG helpers, SQL execution utilities
    docker_backends.py  # Docker container lifecycle (MySQL, PostgreSQL, sqlflite)
    driver_registry.py  # ADBC driver path resolution from ~/.config/adbc/drivers/
    starrocks.py        # StarRocks FE/BE startup detection and log tailing
    tls.py              # TLS certificate generation and sqlflite TLS container
  tests/
    test_sqlite.py      # SQLite catalog lifecycle, data, error handling
    test_duckdb.py       # DuckDB lifecycle, data, missing entrypoint, passthrough
    test_mysql.py        # MySQL lifecycle, data, SHOW TABLES, bad URI, cross-join
    test_postgres.py     # PostgreSQL lifecycle, data, SHOW TABLES, bad URI, TLS
    test_flightsql.py    # FlightSQL lifecycle, data queries, TLS, auth, passthrough
    test_cross_join.py   # Cross-driver JOINs (SQLite x PostgreSQL, SQLite x SQLite)
    test_negative.py     # Validation errors: bad keys, bad paths, duplicates
  reports/               # JSON test reports (gitignored)
```

## How tests work

Each test follows the pattern:
1. `CREATE CATALOG` with the appropriate driver properties
2. Execute queries via the StarRocks MySQL protocol (`pymysql`)
3. Verify results (schema, data, errors)
4. `DROP CATALOG` in teardown

The suite connects to StarRocks at `127.0.0.1:9030` as `root`. StarRocks must be running with ADBC support built in.

## Related

- StarRocks ADBC connector: `feature/adbc-catalog-2` branch on [starrocks](https://github.com/metegenez/starrocks)
- ADBC spec: [apache/arrow-adbc](https://github.com/apache/arrow-adbc)
