# CLAUDE.md - StarRocks ADBC Verification Suite

Integration test suite for the StarRocks ADBC catalog connector.

## Quick Commands

```bash
# Run all tests (requires running StarRocks + STARROCKS_HOME set)
STARROCKS_HOME=/home/mete/coding/opensource/starrocks \
  .venv/bin/pytest tests/ -v --no-header --tb=line

# Run a single module
STARROCKS_HOME=/home/mete/coding/opensource/starrocks \
  .venv/bin/pytest tests/test_sqlite.py -v --tb=short

# Run a single test
STARROCKS_HOME=/home/mete/coding/opensource/starrocks \
  .venv/bin/pytest tests/test_flightsql.py -k "test_name" -v -s --tb=long
```

## Prerequisites

- StarRocks FE+BE must be running at `127.0.0.1:9030` with ADBC support
- `STARROCKS_HOME` env var must point to the StarRocks repo root
- Docker must be available for FlightSQL, MySQL, and PostgreSQL tests
- ADBC drivers installed: `~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql`
- Python venv: `.venv/bin/pip install -e .`

## Project Layout

```
conftest.py           # Session fixtures (StarRocks conn, driver paths, Docker backends)
lib/
  catalog_helpers.py  # CREATE/DROP CATALOG SQL helpers
  docker_backends.py  # Docker container start/stop (MySQL, PostgreSQL, sqlflite)
  driver_registry.py  # Reads driver .so paths from ~/.config/adbc/drivers/*.toml
  starrocks.py        # Detects running StarRocks, tails FE/BE logs
  tls.py              # Generates TLS certs, starts sqlflite with TLS
tests/
  test_sqlite.py      # 6 tests — catalog lifecycle, data, errors
  test_duckdb.py      # 4 tests — lifecycle, data, entrypoint, passthrough
  test_mysql.py       # 5 tests — lifecycle, data, SHOW TABLES, errors, cross-join
  test_postgres.py    # 6 tests — lifecycle, data, SHOW TABLES, errors, TLS, passthrough
  test_flightsql.py   # 5 tests — lifecycle, data, TLS, auth, passthrough
  test_cross_join.py  # 2 tests — cross-driver JOINs
  test_negative.py    # 7 tests — validation error paths
```

## Test Pattern

Every test follows: `CREATE CATALOG` → query via pymysql → assert → `DROP CATALOG`.

Fixtures in `conftest.py` handle:
- StarRocks connectivity (`sr_conn`)
- Driver path resolution (`sqlite_driver_path`, etc.)
- Docker container lifecycle (`mysql_port`, `postgres_port`, `sqlflite_port`, `sqlflite_tls`)
- Log capture on failure (`capture_on_failure`)

## Key Rules

- All catalog interactions go through `lib/catalog_helpers.py` — use `create_adbc_catalog()` and `drop_catalog()`.
- Docker containers use `adbc_test_` prefix for names. They are session-scoped and auto-cleaned.
- Driver paths come from TOML files in `~/.config/adbc/drivers/`. The `driver_registry.py` reads these.
- Property key for authentication is `username` (not `user`).
- The `adbc.*` prefix passes properties through to the ADBC driver directly.
- Tests must not leave catalogs behind — always DROP in teardown/finally.
- The suite expects 35 tests to pass. Any new test module should be added to `tests/` and documented here.
