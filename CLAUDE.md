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
- MySQL Connector/J JAR for the JDBC benchmark catalog: `bash docker/fetch-jdbc-jar.sh` (one-time, fetches `mysql-connector-j-9.3.0.jar` from Maven Central into `docker/drivers/`; gitignored)
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
  tpch/                 # 22 canonical TPC-H queries (q01..q22) with {catalog}.{db} placeholders — Phase 4 single source of truth
  postgres/             # 2 TPC-H queries (select, join) only
  mysql/                # 2 TPC-H queries (select, join) only
  sqlite/, duckdb/, flightsql/  # 2 queries each
  cross-join/           # Cross-driver federation queries
tests/
  test_queries.py             # Executes canonical queries/tpch/ × per-backend product + per-driver dir queries
  test_sqlite.py              # 6 tests — catalog lifecycle, data, errors
  test_duckdb.py              # 4 tests — lifecycle, data, entrypoint, passthrough
  test_mysql.py               # 5 tests — lifecycle, data, SHOW TABLES, errors, cross-join
  test_postgres.py            # 6 tests — lifecycle, data, SHOW TABLES, errors, TLS, passthrough
  test_flightsql.py           # 5 tests — sqlflite path: lifecycle, data, TLS, auth, passthrough
  test_flightsql_starrocks.py # 4 tests — external StarRocks Arrow Flight: lifecycle, data, wrong-password, passthrough (Phase 4)
  test_cross_join.py          # 2 tests — cross-driver JOINs
  test_negative.py            # 7 tests — validation error paths
lib/
  catalog_helpers.py    # create_adbc_catalog(), drop_catalog(), execute_sql() — only file under lib/ post-Phase-4 cleanup
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
- "Cannot invoke "String.split(String)" because "explainString" is null" means backend is not alive in starrocks.

## Phase 2: SF1 Data

Phase 2 replaces the TPC-H seed data (5 rows/table) in PostgreSQL and MySQL with full SF1 data (~900 MB CSV, 8M+ rows). Phase 4 then swaps the generator implementation and consolidates the per-backend query duplicates into a single canonical home:
- `docker/generate-sf1-data.py` — generates SF1 CSV files (8 tables) to `docker/data/sf1/` using the canonical DuckDB `tpch` extension (`INSTALL tpch; LOAD tpch; CALL dbgen(sf=1); COPY <table> TO '<path>' (FORMAT CSV, HEADER TRUE, DELIMITER ',')`). **Generation is fast (≤30s for the full SF1) — no more multi-minute hand-rolled mock generator.** **Run this before first `docker compose up`** — init scripts mount `docker/data/sf1/` and fail if it's empty.
- Init scripts use `\COPY` (PostgreSQL, via psql) and `LOAD DATA INFILE` (MySQL) for bulk loading.
- TPC-H queries live as 22 canonical files under `queries/tpch/q01.sql..q22.sql` with `{catalog}.{db}` template placeholders, substituted at test-collection time. The per-backend skip manifest (e.g. `CANONICAL_SKIPS["postgres"]` for the postgres-numeric Arrow gap) lives at the top of `tests/test_queries.py` — see `.planning/phases/02-*/02-NOTES-postgres-numeric.md` for the StarRocks-side fix that will re-enable the 17 postgres skips. The legacy `queries/postgres/03-q*.sql` and `queries/mysql/03-q*.sql` duplicates were retired in Phase 4.

## Phase 4: External StarRocks Arrow Flight

Phase 4 adds a second StarRocks instance (`sr-external`) to the Compose stack and exercises the StarRocks-native Arrow Flight server end-to-end:
- `sr-external` reuses the same `docker/Dockerfile` and `.deb` as sr-main; no host ports published. Reachable from sr-main via Docker DNS at `sr-external:9408` (FE Arrow Flight).
- TPC-H schema and SF1 data are loaded into native StarRocks tables under the `tpch` database via `INSERT INTO tpch.<table> SELECT * FROM FILES('file:///opt/starrocks/data/sf1/<table>.csv', 'format'='csv', ...)`. The SF1 CSVs (now generated by the DuckDB `tpch` extension — see Phase 2 above) feed both backends.
- A new ADBC catalog `sr_flightsql_starrocks` connects from sr-main to `grpc://sr-external:9408` with `username=root` / `password=""`. All 22 canonical TPC-H queries (`queries/tpch/q01..q22.sql`) target it via the `flightsql-starrocks` backend in `tests/test_queries.py`'s `CANONICAL_BACKENDS` mapping.
- `tests/test_flightsql_starrocks.py` covers 4 scenarios (lifecycle, data, wrong-password, ADBC pass-through); the existing sqlflite path (`sr-flightsql`, `sr-flightsql-tls`, `tests/test_flightsql.py`) coexists unchanged.
- Cleanup: dead `lib/` files left over from Phase 1 (`docker_backends.py`, `starrocks.py`, `tls.py`, `driver_registry.py`) are deleted; `lib/` retains only `__init__.py` and `catalog_helpers.py`.

## Pitfalls (read these before running `./run-verify.py` or `docker compose up`)

These are real failures hit while bringing the SF1 stack up. Don't relearn them.

### Pre-flight

- **Generate SF1 CSVs first.** `cd docker && python3 generate-sf1-data.py` writes ~900 MB to `docker/data/sf1/`. Without this, `postgres`/`mysql` init scripts try to load nonexistent files and the containers exit. Generator is deterministic (`random.seed(42)`); regenerating is safe and idempotent.
- **Lineitem generation takes ~2 minutes.** The script announces "Generating lineitem (this takes a few minutes)" so you'll know it's not hung.
- **Don't commit the SF1 CSVs.** They're in `.gitignore` (~900 MB). Each contributor regenerates.

### `docker/data/sf1/` ownership trap

The MySQL container's entrypoint runs as UID 999 (`mysql`) and chowns `/var/lib/mysql-files/`. Because that path is bind-mounted from the host, **after MySQL starts, the host CSV files are owned by UID 999** (which on the host typically maps to some unrelated system user). Re-running `generate-sf1-data.py` from the host then fails with `PermissionError`.

Fix from the host (no sudo):
```bash
docker run --rm -v $(pwd)/docker/data/sf1:/sf1 alpine \
  chown -R $(id -u):$(id -g) /sf1
```

### Volume mount: do NOT add `:ro` to the SF1 mount

```yaml
- ./data/sf1/:/var/lib/mysql-files/      # OK
- ./data/sf1/:/var/lib/mysql-files/:ro   # BREAKS — mysql:8.0 entrypoint exits 1
```
The MySQL entrypoint chowns `/var/lib/mysql-files/` even when it doesn't need to write the CSVs. `chown` on a read-only mount returns EROFS and the entrypoint's `set -e` aborts. Postgres' `\COPY` is fine with `:ro` because postgres doesn't chown.

### CSV line endings: must be LF, not CRLF

Python's `csv.writer` defaults to `lineterminator="\r\n"`. MySQL `LOAD DATA INFILE` with `LINES TERMINATED BY '\n'` then leaves a stray `\r` inside the last field of each row, which corrupts quoted fields and triggers `Data too long for column ... at row 2` for region's quoted comments. Always pass `lineterminator="\n"` explicitly when generating CSVs for MySQL bulk load.

### MySQL healthcheck: TCP, not socket

`mysqladmin ping --silent` answers via the unix socket the moment the temporary server starts — *before* MySQL has finished `02-data.sql` and *before* the TCP listener on port 3306 is bound. StarRocks ADBC catalog connects over TCP, so a "healthy" MySQL container can still refuse the catalog with `connection refused: dial tcp 10.x.x.x:3306`. The compose file uses `mysql --protocol=TCP -e "SELECT 1"` for the healthcheck so it actually tests what tests need.

`start_period: 300s` covers the SF1 lineitem load. Don't shorten it.

### MySQL connection limit

Each pytest test creates a fresh ADBC catalog → new connection to the MySQL backend. The full suite (~90 tests) blows past MySQL's default `max_connections=151` mid-run, surfacing as `Error 1040: Too many connections: BE:10001`. The compose file pins `--max-connections=500`. If you change topology (more tests, multiple parallel workers), bump it again.

### StarRocks FE can SIGSEGV on malformed queries

A query that references a column from a table not yet joined (e.g., `JOIN supplier ON s_nationkey = n_nationkey` *before* `nation` is joined) tripped a JNI crash in StarRocks FE during this phase. The container reports "healthy" afterwards because the healthcheck cached its OK from earlier, but the Java process is `<defunct>` and every connection fails with `Lost connection to MySQL server at 'reading initial communication packet'`.

Recovery — data persists, only FE in-memory state is lost:
```bash
docker compose -f docker/docker-compose.yml restart sr-main
until mysql --protocol=TCP -uroot -h127.0.0.1 -P9030 -e "SELECT 1" 2>/dev/null | grep -q 1; do sleep 3; done
```
Catalogs auto-recreate via test fixtures.

### `run-verify.py` quirks

- The CLI documents `./run-verify.py docker/X.deb docker/Y.deb` but the script copies the inputs into `docker/`. Same-file copy raised `SameFileError` until `9103eab` fixed it.
- The script invokes pytest via `sys.executable`, which is the **system Python** (no pytest installed). Either run as `.venv/bin/python ./run-verify.py ...` or skip the wrapper and invoke `.venv/bin/pytest tests/ -v` directly after `docker compose up -d`.
- The healthcheck loop accepts services without a healthcheck (`Health == ""` + `State == "running"`) as ready. `sr-flightsql` and `sr-flightsql-tls` are intentionally healthcheck-free; don't tighten the loop to `Health == "healthy"` only or it will time out.

### Stack lifecycle

- Default mode is `--keep`: containers stay running after pytest. Good for `pytest -k <single_test>` iteration. **Run `docker compose -f docker/docker-compose.yml down -v` when done** — `-v` is important; without it named volumes survive and the next `up` skips init scripts on warm restart, masking init bugs.
- A cold `up` from empty volumes takes ~4 minutes (StarRocks FE+BE warmup + SF1 load on both backends in parallel). Iterating on test code? Use `--skip-rebuild` if the StarRocks `.deb`s haven't changed.

### Postgres-numeric Arrow gap

17 postgres TPC-H queries are intentionally skipped — StarRocks BE has no decoder for `arrow.opaque[storage_type=string, type_name=numeric, vendor_name=PostgreSQL]`. The mysql versions of the same queries pass. **Do not "fix" this by removing the skips**; the fix lives in StarRocks BE (registry of extension-type decoders). Full design doc at `.planning/phases/02-*/02-NOTES-postgres-numeric.md`.

### Skip directive in query files

`tests/test_queries.py` honors a `-- Skip: <reason>` line anywhere in a `.sql` file (parsed before query execution; comments-only files would still need the skip after the standard `-- TPC-H Q...` header). Use this for queries that depend on engine work not yet landed. Removing the line re-enables the test.

### StarRocks DUPLICATE KEY column ordering (Phase 4)

`CREATE TABLE ... DUPLICATE KEY(col_a, col_d) DISTRIBUTED BY HASH(...)` fails with `Key columns must be the first few columns of the schema` if the named columns aren't a contiguous prefix of the schema declaration order. **Do NOT add `DUPLICATE KEY` to the sr-external TPC-H DDL.** StarRocks auto-picks the first 1-3 columns (e.g., `(l_orderkey, l_partkey, l_suppkey)` for lineitem), which is correct for these query patterns. Full rationale: `.planning/phases/04-*/04-RESEARCH.md` Pitfall 1.

### `run-verify.py` service dict (Phase 4)

`run-verify.py:_wait_for_healthy()` has a hardcoded `services = {...}` dict around line 183 that gates pytest launch on every listed service flipping green. **Adding a new compose service requires adding it to this dict** — otherwise the runner returns success before the new service is healthy and pytest fires too early, surfacing as `Database 'tpch' doesn't exist` on first run / passes on retry. sr-external is included as of Phase 4. Full rationale: `.planning/phases/04-*/04-RESEARCH.md` Pitfall 7.
