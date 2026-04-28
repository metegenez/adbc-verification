# CLAUDE.md — StarRocks ADBC Verification Suite

Integration test suite for the StarRocks ADBC catalog connector. Docker Compose is the **only** execution path — no local StarRocks, no `STARROCKS_HOME`.

## Quick Commands

```bash
# Full cycle: build containers, run all tests (from project root)
./run-verify.py docker/starrocks-fe_latest_amd64.deb docker/starrocks-be_latest_amd64.deb

# Start environment without running tests
docker compose -f docker/docker-compose.yml up -d

# Run all tests against running containers
STARROCKS_HOST=127.0.0.1 STARROCKS_PORT=9030 .venv/bin/pytest tests/ -v

# Run a single module
.venv/bin/pytest tests/test_postgres.py -v --tb=short

# Run a single test
.venv/bin/pytest tests/test_flightsql.py -k "test_name" -v -s --tb=long

# Run query file tests (auto-discovers all .sql under queries/)
.venv/bin/pytest tests/test_queries.py -v

# Stop and clean up
docker compose -f docker/docker-compose.yml down -v
```

## Prerequisites

- Docker and Docker Compose v2
- StarRocks `.deb` packages in `docker/` (build via `ship-starrocks` skill)
- ADBC drivers installed: `~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql`
- Driver `.so` files in `docker/drivers/` (copy from `~/.config/adbc/drivers/`)
- Python venv: `.venv/bin/pip install -e .`
- Pre-baked data: `python docker/generate-data.py`

## Project Layout

```
docker/
  docker-compose.yml    # 5 services on sr-net bridge network
  Dockerfile            # StarRocks from ubuntu:24.04 .deb install
  entrypoint.sh         # FE+BE startup sequence
  init/                 # Backend init SQL (auto-executed at startup)
    postgres/           # 01-schema.sql + 02-data.sql (TPC-H schema + SF1)
    mysql/              # 01-schema.sql + 02-data.sql (TPC-H schema + SF1)
    sqlflite/           # TPC-H schema
  data/                 # Pre-baked .db files + SF1 CSVs
    tpch_sqlite.db, tpch_duckdb.db, etc.
    sf1/                # SF1 CSV data for PostgreSQL and MySQL (Phase 2)
  certs/                # TLS certificates
  drivers/              # ADBC driver .so files
  generate-data.py      # Regenerate .db and CSV files
queries/                # Externalized SQL files (auto-discovered by test_queries.py)
  postgres/             # 2 TPC-H queries (select, join) — 22 planned in Phase 2
  mysql/                # 2 TPC-H queries (select, join) — 22 planned in Phase 2
  sqlite/, duckdb/, flightsql/  # 2 queries each
  cross-join/           # Cross-driver federation queries
tests/
  test_queries.py       # Executes every .sql under queries/ against live catalogs
  test_sqlite.py        # 6 tests — catalog lifecycle, data, errors
  test_duckdb.py        # 4 tests — lifecycle, data, entrypoint, passthrough
  test_mysql.py         # 5 tests — lifecycle, data, SHOW TABLES, errors, cross-join
  test_postgres.py      # 6 tests — lifecycle, data, SHOW TABLES, errors, TLS, passthrough
  test_flightsql.py     # 5 tests — lifecycle, data, TLS, auth, passthrough
  test_cross_join.py    # 2 tests — cross-driver JOINs
  test_negative.py      # 7 tests — validation error paths
lib/
  catalog_helpers.py    # create_adbc_catalog(), drop_catalog(), execute_sql()
  driver_registry.py    # Reads driver .so paths from ~/.config/adbc/drivers/*.toml
conftest.py             # Session fixtures (sr_conn, driver paths, Docker Compose)
run-verify.py           # CLI runner — ship→verify→retest loop
```

## Architecture

StarRocks runs in a single container (`sr-main`) co-locating FE+BE. All 5 ADBC drivers are baked into the container image at `/opt/starrocks/drivers/`. Backend databases (PostgreSQL, MySQL, FlightSQL) run as separate Compose services. The host runs pytest, connecting to StarRocks on port 9030 (published from the container). StarRocks connects to backends via Docker DNS service names (`sr-postgres`, `sr-mysql`, `sr-flightsql`).

## Test Pattern

Every test follows: `CREATE CATALOG` → query via pymysql → assert → `DROP CATALOG`.

Fixtures in `conftest.py` provide:
- `sr_conn` — pymysql connection to StarRocks (session-scoped)
- `sqlite_driver_path`, `postgres_driver_path`, etc. — fixed paths to `/opt/starrocks/drivers/libadbc_driver_*.so` (NOT resolved at runtime)
- `capture_on_failure` — on test failure, runs `docker compose logs --tail=50` for all services
- Catalog fixtures (`sr_postgres_cat`, `sr_mysql_cat`, etc.) — session-scoped, created once, dropped on teardown

## test_queries.py Conventions

`tests/test_queries.py` auto-discovers all `.sql` files under `queries/` and executes them. Each `.sql` file must:
- Use fully-qualified catalog names (`sr_postgres.public.region`, `sr_mysql.testdb.orders`)
- Optionally include `-- Expected: N rows` for automated row count assertion
- Start any comments with `--` prefix

SQL files are parametrized by driver directory name (top-level under `queries/`). The directory name is available as the `driver` param in the test — used for skip logic (e.g., DuckDB `:memory:` has no TPC-H tables).

## Key Rules

- All catalog interactions go through `lib/catalog_helpers.py` — use `create_adbc_catalog()` and `drop_catalog()`.
- Docker Compose is the **only** execution path. There is no local/manual StarRocks mode.
- Driver paths are **fixed** at `/opt/starrocks/drivers/libadbc_driver_*.so` — no TOML resolution at runtime. Driver registry is build-time only.
- Property key for authentication is `username` (not `user`).
- The `adbc.*` prefix passes properties through to the ADBC driver directly.
- Tests must not leave catalogs behind — always DROP in teardown/finally.
- The suite expects 35 pytest tests to pass, plus all query file tests under `queries/`.
- Query files go in `queries/{driver}/` and are picked up automatically — no test code changes needed.

## Phase 2: SF1 Data (Current)

Phase 2 replaces the TPC-H seed data (5 rows/table) in PostgreSQL and MySQL with full SF1 data (~1GB, 8M+ rows):
- `docker/generate-sf1-data.py` — generates SF1 CSV files (8 tables) to `docker/data/sf1/`
- Init scripts use `COPY` (PostgreSQL) and `LOAD DATA INFILE` (MySQL) for bulk loading
- 44 TPC-H query files (22 per backend) in `queries/postgres/` and `queries/mysql/`
- SF1 data is **not yet implemented** — plan ready at `.planning/phases/02-*/02-01-PLAN.md`

## Retired

| File | Reason |
|------|--------|
| `lib/docker_backends.py` | Replaced by `docker-compose.yml` services + healthchecks |
| `lib/starrocks.py` (subprocess start) | Replaced by Docker Compose |
| `lib/starrocks.py` (file log tail) | Replaced by `docker compose logs` |
| `lib/tls.py` | Replaced by pre-generated certs in `docker/certs/` |
| `STARROCKS_HOME` env var | Replaced by `STARROCKS_HOST`/`STARROCKS_PORT` |
