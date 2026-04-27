# StarRocks ADBC Verification Suite

Docker Compose-based end-to-end verification suite for the StarRocks ADBC catalog stack. Ships a StarRocks DEB into a container alongside backend data sources (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB, SQLite), then runs TPC-H and cross-driver join queries through the StarRocks ADBC catalog layer. One command: `./run-verify.py fe.deb be.deb`.

## Quick Start

### Prerequisites

- Docker and Docker Compose v2
- Python 3.11+ with venv
- StarRocks `.deb` packages (FE + BE), build via `ship-starrocks` skill
- ADBC drivers installed via `dbc install`

### One-Time Setup

```bash
# 1. Create Python venv and install deps
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Install ADBC drivers (5 drivers)
~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql

# 3. Copy driver .so files to docker/
mkdir -p docker/drivers
python -c "
from lib.driver_registry import get_all_driver_paths
import shutil
for name, path in get_all_driver_paths().items():
    shutil.copy2(path, f'docker/drivers/libadbc_driver_{name}.so')
    print(f'  {name}: {path} -> docker/drivers/')
"

# 4. Generate pre-baked test data and TLS certificates
python docker/generate-data.py
```

### Full Verification Cycle

```bash
# Build StarRocks from source, package as .deb, then verify
./run-verify.py /path/to/starrocks-fe.deb /path/to/starrocks-be.deb
```

Copies `.deb` packages, builds Docker containers, waits for healthchecks, runs all tests, and reports results.

### Fast Iteration

Containers stay running by default (`--keep`). For fast re-testing without rebuild:

```bash
# Copy new .debs and rebuild just the StarRocks container
cp /path/to/new-fe.deb docker/starrocks-fe_latest_amd64.deb
cp /path/to/new-be.deb docker/starrocks-be_latest_amd64.deb
docker compose -f docker/docker-compose.yml up -d --build sr-main

# Re-run tests (containers stay running)
.venv/bin/pytest tests/ -v

# Run a subset of tests
.venv/bin/pytest tests/ -k flightsql -v
.venv/bin/pytest tests/ -k "sqlite or duckdb" -v
.venv/bin/pytest tests/ -k "not tls" -v
```

## Running Tests Directly

After `docker compose up` (containers running):

```bash
source .venv/bin/activate
export STARROCKS_HOST=127.0.0.1 STARROCKS_PORT=9030

# All tests
pytest tests/ -v

# Single module
pytest tests/test_postgres.py -v

# Single test
pytest tests/test_flightsql.py -k "test_name" -v -s

# Query file tests
pytest tests/test_queries.py -v
```

## Project Structure

```
docker/
  docker-compose.yml    # 5 services on sr-net bridge network
  Dockerfile            # StarRocks container from ubuntu:24.04 with .deb install
  entrypoint.sh         # FE+BE startup, BE registration
  init/                 # Backend init SQL (auto-executed at container startup)
    postgres/           # TPC-H schema + SF1 data
    mysql/              # TPC-H schema + SF1 data
    sqlflite/           # SQLite-compatible TPC-H schema (8 tables)
  data/                 # Pre-baked .db files + SF1 CSVs
  certs/                # Self-signed TLS certificates
  drivers/              # ADBC driver .so files (copied from host at build time)
  generate-data.py      # Generate SQLite/DuckDB .db files
queries/                # Externalized SQL query files (versioned independently)
  sqlite/               # TPC-H queries against SQLite catalog
  postgres/             # 22 TPC-H queries against PostgreSQL catalog
  mysql/                # 22 TPC-H queries against MySQL catalog
  flightsql/            # TPC-H queries against FlightSQL catalog
  duckdb/               # TPC-H queries against DuckDB catalog
  cross-join/           # Cross-driver federation queries
tests/                  # pytest test suite (35 tests + query discovery)
  test_queries.py       # Auto-discovers and runs all .sql files under queries/
lib/                    # Helper modules
  catalog_helpers.py    # CREATE/DROP CATALOG SQL helpers
  driver_registry.py    # ADBC driver path resolution (build-time only)
conftest.py             # pytest fixtures (Docker Compose-aware)
run-verify.py           # CLI runner — ship→verify→retest loop
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STARROCKS_HOST` | `127.0.0.1` | StarRocks FE host (port 9030 published from container) |
| `STARROCKS_PORT` | `9030` | StarRocks FE MySQL port |

## Docker Compose Services

| Service | Port (internal) | Host Port | Description |
|---------|-----------------|-----------|-------------|
| `sr-main` | 9030 | 9030 | StarRocks FE+BE with 5 ADBC drivers |
| `sr-postgres` | 5432 | — | PostgreSQL 16 with TPC-H data |
| `sr-mysql` | 3306 | — | MySQL 8.0 with TPC-H data |
| `sr-flightsql` | 31337 | — | FlightSQL (sqlflite) without TLS |
| `sr-flightsql-tls` | 31337 | 31338 | FlightSQL (sqlflite) with TLS |

All services communicate via Docker DNS on the `sr-net` bridge network.

## Test Coverage

- **35 tests** across 7 modules (catalog lifecycle, data, error paths)
- **5 ADBC drivers**: SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL
- **TPC-H queries**: SELECT + JOIN across all drivers, plus 44 SF1 query files
- **Cross-driver federation**: SQLite↔PostgreSQL, SQLite↔SQLite JOINs
- **TLS**: FlightSQL and PostgreSQL with self-signed certificates
- **Error paths**: Bad URIs, wrong passwords, missing entrypoints, unknown keys

## Available pytest Markers

| Marker | Description |
|--------|-------------|
| `sqlite` / `flightsql` / `postgres` / `duckdb` / `mysql` | Per-driver tests |
| `cross_join` | Cross-driver federation tests |
| `negative` | Error path validation tests |
| `tls` | TLS-enabled tests |

## CLI Reference

```
usage: run-verify.py [-h] [--keep | --cleanup] [--subset FILTER]
                     [--report FILE] [--skip-rebuild]
                     fe_deb be_deb

StarRocks ADBC Verification Suite — ship→verify→retest loop

positional arguments:
  fe_deb           Path to starrocks-fe .deb package
  be_deb           Path to starrocks-be .deb package

options:
  -h, --help       show this help message and exit
  --keep           Leave containers running after tests (default)
  --cleanup        Run docker compose down after tests
  --subset FILTER  Pass filter to pytest -k (e.g., "flightsql")
  --report FILE    Write JSON report to FILE (default: reports/latest.json)
  --skip-rebuild   Skip docker compose build (reuse existing images)
```

### Examples

```bash
# Full cycle, leave containers running
./run-verify.py /tmp/starrocks-fe_3.4_amd64.deb /tmp/starrocks-be_3.4_amd64.deb

# Run only FlightSQL tests, clean up after
./run-verify.py --subset flightsql --cleanup fe.deb be.deb

# Skip rebuild (reuse cached image), save report
./run-verify.py --skip-rebuild --report report-v2.json fe.deb be.deb
```

## Troubleshooting

- **Tests fail but containers are healthy**: `docker compose -f docker/docker-compose.yml logs sr-main --tail=50`
- **Container won't start**: Ensure `.deb` files exist in `docker/`, check `docker compose ps`
- **Driver not found**: Verify `.so` files are in `docker/drivers/` matching names in `conftest.py`
- **Port conflict**: Port 9030 must be free; override with `STARROCKS_PORT` env var
