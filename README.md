# StarRocks ADBC Verification Suite

Docker Compose-based end-to-end verification suite for the StarRocks ADBC catalog stack. Ships a StarRocks DEB into a container alongside backend data sources (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB, SQLite), then runs TPC-H and cross-driver join queries through the StarRocks ADBC catalog layer.

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

This copies `.deb` packages, builds Docker containers, waits for healthchecks, runs all tests, and reports results.

### Fast Iteration

Containers stay running by default (`--keep`). For fast re-testing without rebuild:

```bash
# Copy new .debs and rebuild just the StarRocks container
cp /path/to/new-fe.deb docker/starrocks-fe_latest_amd64.deb
cp /path/to/new-be.deb docker/starrocks-be_latest_amd64.deb
docker compose -f docker/docker-compose.yml up -d --build sr-main

# Re-run tests (containers stay running)
pytest tests/ -v

# Run a subset of tests
pytest tests/ -k flightsql -v
pytest tests/ -k "sqlite or duckdb" -v
pytest tests/ -k "not tls" -v
```

### Available pytest Markers

| Marker | Description |
|--------|-------------|
| `sqlite` | SQLite backend tests |
| `flightsql` | FlightSQL backend tests |
| `postgres` | PostgreSQL backend tests |
| `duckdb` | DuckDB backend tests |
| `mysql` | MySQL backend tests |
| `cross_join` | Cross-driver federation tests |
| `negative` | Error path validation tests |
| `tls` | TLS-enabled tests |

## Project Structure

```
docker/
  docker-compose.yml    # Service definitions (5 services on sr-net bridge)
  Dockerfile            # StarRocks container from ubuntu:24.04 with .deb install
  entrypoint.sh         # FE+BE startup, priority_networks, BE registration
  init/                 # Backend init SQL (auto-executed at container startup)
    postgres/           # TPC-H schema + seed data (8 tables)
    mysql/              # TPC-H schema + seed data (8 tables)
    sqlflite/           # SQLite-compatible TPC-H schema (8 tables)
  data/                 # Pre-baked .db files (copied into StarRocks image)
  certs/                # Self-signed TLS certificates (FlightsQL, PostgreSQL)
  drivers/              # ADBC driver .so files (copied from host)
  generate-data.py      # Script to regenerate all .db files
queries/                # Externalized SQL query files (versioned independently)
  sqlite/               # TPC-H SELECT + JOIN against SQLite catalog
  postgres/             # TPC-H SELECT + JOIN against PostgreSQL catalog
  mysql/                # TPC-H SELECT + JOIN against MySQL catalog
  flightsql/            # TPC-H SELECT + JOIN against FlightSQL catalog
  duckdb/               # TPC-H SELECT + JOIN against DuckDB catalog
  cross-join/           # Cross-driver federation queries
tests/                  # pytest test suite (35 tests across 7 modules)
lib/                    # Helper modules
  catalog_helpers.py    # CREATE/DROP CATALOG SQL helpers
  driver_registry.py    # ADBC driver path resolution (build-time only)
  starrocks.py          # Thin pymysql connection wrapper
conftest.py             # pytest fixtures (docker compose-aware)
run-verify.py           # CLI runner — ship→verify→retest loop
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STARROCKS_HOST` | `127.0.0.1` | StarRocks FE MySQL host (port 9030 published from container) |
| `STARROCKS_PORT` | `9030` | StarRocks FE MySQL port |
| `FLIGHTSQL_CA_CERT` | `docker/certs/flightsql-ca.pem` | FlightSQL TLS CA certificate path |
| `POSTGRES_CA_CERT` | `docker/certs/postgres-ca.pem` | PostgreSQL TLS CA certificate path |

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

## Docker Compose Services

All services run on the `sr-net` bridge network and communicate via Docker DNS:

| Service | Container | Port (internal) | Host Port | Description |
|---------|-----------|-----------------|-----------|-------------|
| `sr-main` | `sr-main` | 9030, 8030, 9408, 9050, 9419 | 9030 | StarRocks FE+BE with all 5 ADBC drivers |
| `sr-postgres` | `sr-postgres` | 5432 | — | PostgreSQL 16 with TPC-H data |
| `sr-mysql` | `sr-mysql` | 3306 | — | MySQL 8.0 with TPC-H data |
| `sr-flightsql` | `sr-flightsql` | 31337 | — | FlightSQL (sqlflite) without TLS |
| `sr-flightsql-tls` | `sr-flightsql-tls` | 31337 | 31338 | FlightSQL (sqlflite) with TLS |

## Test Coverage

- **35 tests** across 7 test modules
- **5 ADBC drivers**: SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL
- **TPC-H queries**: SELECT + JOIN across all drivers
- **Cross-driver federation**: SQLite↔PostgreSQL, SQLite↔SQLite JOINs
- **TLS**: FlightSQL and PostgreSQL with self-signed certificates
- **Error paths**: Bad URIs, wrong passwords, missing entrypoints, unknown keys

## Troubleshooting

- **Tests fail but containers are healthy**: Check `docker compose logs sr-main --tail=50` for StarRocks errors
- **Container won't start**: Ensure `.deb` files exist in `docker/` directory, check `docker compose ps`
- **Driver not found**: Verify driver `.so` files are in `docker/drivers/` and match names in `conftest.py`
- **Port conflict**: Port 9030 must be free on host; change via `STARROCKS_PORT` env var
