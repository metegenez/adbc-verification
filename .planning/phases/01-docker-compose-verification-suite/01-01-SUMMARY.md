---
phase: 01-docker-compose-verification-suite
plan: 01
subsystem: infra
tags: [docker, compose, starrocks, adbc, test-infrastructure]

requires: []
provides:
  - Docker Compose environment with 5 services on sr-net bridge network
  - StarRocks container built from .deb with baked-in ADBC drivers
  - Backend init SQL scripts for PostgreSQL, MySQL with TPC-H seed data
  - Pre-baked SQLite and DuckDB database files
  - Self-signed TLS certificates for FlightSQL and PostgreSQL
  - Refactored conftest.py with env var config and fixed driver paths
  - All test files updated to Docker Compose service names
affects: [02-data-loading, 03-developer-experience]

tech-stack:
  added: [docker, docker-compose, openssl]
  patterns:
    - Container-internal driver paths as module-level constants
    - Docker DNS service names in test URIs
    - Pre-baked .db files for stateless data sources
    - Init SQL scripts for server-based backends

key-files:
  created:
    - docker/docker-compose.yml
    - docker/Dockerfile
    - docker/entrypoint.sh
    - docker/init/postgres/01-schema.sql
    - docker/init/postgres/02-data.sql
    - docker/init/mysql/01-schema.sql
    - docker/init/mysql/02-data.sql
    - docker/init/mysql/03-cross-join.sql
    - docker/generate-data.py
    - docker/data/test_sqlite.db
    - docker/data/cross_sqlite_a.db
    - docker/data/cross_sqlite_b.db
    - docker/data/tpch_duckdb.db
    - docker/certs/flightsql-ca.pem
    - docker/certs/flightsql-ca.key
    - docker/certs/postgres-ca.pem
    - docker/certs/postgres-ca.key
  modified:
    - conftest.py
    - lib/starrocks.py
    - lib/docker_backends.py
    - lib/tls.py
    - lib/driver_registry.py
    - tests/test_sqlite.py
    - tests/test_mysql.py
    - tests/test_postgres.py
    - tests/test_flightsql.py
    - tests/test_duckdb.py
    - tests/test_cross_join.py

key-decisions:
  - "Docker Compose as the sole orchestration layer — no subprocess container management"
  - "Driver paths as fixed /opt/starrocks/drivers/ constants — no TOML resolution at runtime"
  - "SQLite/DuckDB data pre-baked into container image — no runtime data generation"
  - "PostgreSQL/MySQL data loaded via init scripts — idempotent with ON CONFLICT DO NOTHING"
  - "Self-signed TLS certs pre-generated — no runtime cert extraction from containers"

requirements-completed: [DC-01, DC-02, DC-03, DC-04, VAL-01, VAL-02, VAL-03, VAL-04, VAL-05, VAL-07]

duration: 15min
completed: 2026-04-27
---

# Phase 01 Plan 01: Docker Compose Foundation Summary

**Self-contained Docker Compose environment with 5 services on sr-net bridge network — StarRocks from .deb with baked-in ADBC drivers, backend data pre-loaded, conftest refactored to zero-subprocess startup**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-27T13:55:32Z
- **Completed:** 2026-04-27T14:10:37Z
- **Tasks:** 3
- **Files created:** 17
- **Files modified:** 11

## Accomplishments

- Docker Compose file with 5 services (sr-main, sr-postgres, sr-mysql, sr-flightsql, sr-flightsql-tls) on sr-net bridge network with healthchecks
- StarRocks Dockerfile from ubuntu:24.04 with .deb install, ADBC driver baking, and container-internal file paths
- Entrypoint script with FE+BE sequential startup, priority_networks patching, BE registration, and init SQL execution
- Backend init SQL scripts for PostgreSQL and MySQL with TPC-H schema (region, nation, orders, lineitem), test_data, and departments tables
- Pre-baked SQLite databases (test_sqlite.db, cross_sqlite_a.db, cross_sqlite_b.db) and DuckDB TPC-H database (tpch_duckdb.db)
- Self-signed TLS certificates for FlightSQL and PostgreSQL in docker/certs/
- Conftest refactored: STARROCKS_HOST/STARROCKS_PORT env vars, fixed driver paths at /opt/starrocks/drivers/, docker compose logs capture, static port fixtures
- All 7 test modules updated: URIs use Docker DNS service names, subprocess data creation removed
- Deprecated modules: lib/docker_backends.py, lib/tls.py; simplified lib/starrocks.py to connect-only helper

## Task Commits

1. **Task 1: Docker infrastructure** - `4c1a9d2` (feat)
2. **Task 2: Backend init scripts, data, and certs** - `01bc6c9` (feat)
3. **Task 3: Refactor conftest and retire old modules** - `7fdff49` (refactor)

## Files Created/Modified

- `docker/docker-compose.yml` — 5 services on sr-net with healthchecks
- `docker/Dockerfile` — ubuntu:24.04 with .deb install and driver baking
- `docker/entrypoint.sh` — FE+BE startup, priority_networks, BE registration, init SQL
- `docker/init/postgres/` — TPC-H schema + seed data + test_data + departments
- `docker/init/mysql/` — TPC-H schema + seed data + test_data + departments
- `docker/generate-data.py` — Reproducible SQLite/DuckDB database creation
- `docker/data/` — Pre-baked .db files for SQLite (3) and DuckDB (1)
- `docker/certs/` — Self-signed TLS certs for flightsql and postgres
- `conftest.py` — Rewritten for Docker Compose: env vars, fixed paths, compose logs
- `lib/starrocks.py` — Simplified to connect() wrapper
- All `tests/test_*.py` — Updated URIs to Docker service names

## Decisions Made

- Used Docker Compose as the sole orchestration layer, retiring individual container management
- Fixed driver paths at `/opt/starrocks/drivers/` — no TOML resolution at runtime (used at build time only)
- Pre-baked SQLite/DuckDB data into container image for stateless data sources
- PostgreSQL/MySQL data loaded via init scripts with idempotent inserts (ON CONFLICT DO NOTHING / INSERT IGNORE)
- Self-signed TLS certs pre-generated with openssl; no runtime extraction from containers

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Infrastructure and test framework are fully adapted for Docker Compose. Ready for Plan 01-02 (TPC-H depth and cross-driver join queries) which builds on the Compose environment to load expanded TPC-H data and externalize query files.

---
*Plan: 01-01*
*Completed: 2026-04-27*
