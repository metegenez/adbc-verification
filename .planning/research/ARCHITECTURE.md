# Architecture Research

**Domain:** Docker Compose-based database verification suite (StarRocks ADBC)
**Researched:** 2026-04-27
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                           HOST (pytest runner)                        │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │  tests/*.py      │  │  conftest.py     │  │  queries/*.sql   │    │
│  │  (35 test cases) │  │  (fixtures)      │  │  (TPC-H corpus)  │    │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘    │
│           │                     │                      │             │
│           └──────────┬──────────┘                      │             │
│                      │ MySQL protocol (port 9030)       │ read at     │
│                      │ 127.0.0.1:9030                   │ test time   │
└──────────────────────┼──────────────────────────────────┼─────────────┘
                       │                                  │
              ┌────────▼────────┐                         │
              │  docker/         │                         │
              │  queries/        │ ◄───────────────────────┘
              │  (mount: ro)     │
              └─────────────────┘
                       │
┌─ Docker bridge network: sr-net ─────────────────────────────────────┐
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                sr-main (StarRocks FE+BE from DEB)             │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐  │   │
│  │  │ FE :9030     │  │ BE :9060     │  │ ADBC Drivers:      │  │   │
│  │  │ Flight :9408 │  │ Flight :9419 │  │ /opt/starrocks/    │  │   │
│  │  └──────────────┘  └──────────────┘  │   drivers/         │  │   │
│  │                                      │ ├ flightsql.so     │  │   │
│  │  ┌────────────────────────────────┐  │ ├ postgresql.so    │  │   │
│  │  │  /opt/starrocks/data/          │  │ ├ mysql.so         │  │   │
│  │  │  ├ duckdb_tpch.db  (local)     │  │ ├ sqlite.so        │  │   │
│  │  │  └ sqlite_tpch.db  (local)     │  │ └ duckdb.so        │  │   │
│  │  └────────────────────────────────┘  └────────────────────┘  │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│         ADBC driver calls via Docker network (service names)         │
│                         │                                            │
│     ┌───────────────────┼───────────────────┐                        │
│     │                   │                   │                        │
│  ┌──▼──────────┐  ┌─────▼──────┐  ┌────────▼────────┐               │
│  │ sr-pg       │  │ sr-mysql   │  │ sr-flightsql    │               │
│  │ postgres:16 │  │ mysql:8.0  │  │ sqlflite:latest │               │
│  │ :5432       │  │ :3306      │  │ :31337          │               │
│  │             │  │            │  │ :31338 (TLS)    │               │
│  │ TPC-H       │  │ TPC-H      │  │ TPC-H           │               │
│  │ preloaded   │  │ preloaded  │  │ preloaded       │               │
│  └─────────────┘  └────────────┘  └─────────────────┘               │
│                                                                      │
│  File-based backends (no container needed):                          │
│  ┌─────────────────────────────────────────┐                         │
│  │ DuckDB & SQLite: .db files inside         │                         │
│  │ sr-main at /opt/starrocks/data/           │                         │
│  │ ADBC driver opens .db directly            │                         │
│  └─────────────────────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Runtime Location | Responsibility | Implementation |
|-----------|-----------------|----------------|----------------|
| **pytest runner** | Host | Execute test suite, assert results, capture logs | Python 3.11+, pytest 9.x, pymysql |
| **conftest.py** | Host | Session-scoped fixtures: StarRocks connection, catalog create/drop, driver paths | Adapted to read config from env vars, connect via published port |
| **queries/*.sql** | Host (read), mounted into sr-main (ro) | TPC-H query corpus and cross-driver join test queries | Standalone SQL files, parameterizable via env vars |
| **ship→verify script** | Host | Orchestrate: copy DEB → `docker compose up --build` → run tests → report | Bash or Python CLI, accepts DEB path |
| **sr-main** | Docker container | StarRocks query engine (FE+BE co-located), ADBC driver host | Built from `.deb`, entrypoint script starts FE→BE→register |
| **sr-pg** | Docker container | PostgreSQL 16 data source with TPC-H schema/data | stock `postgres:16` image, init SQL mounted |
| **sr-mysql** | Docker container | MySQL 8.0 data source with TPC-H schema/data | stock `mysql:8.0` image, init SQL mounted |
| **sr-flightsql** | Docker container | FlightSQL data source (sqlflite) with TPC-H data | `voltrondata/sqlflite:latest`, init SQL mounted |
| **DuckDB .db** | File inside sr-main | DuckDB data source (embedded, no server) | Pre-built `.db` file with TPC-H schema+data |
| **SQLite .db** | File inside sr-main | SQLite data source (embedded, no server) | Pre-built `.db` file with TPC-H schema+data |
| **docker-compose.yml** | Host | Define all services, networks, volumes, healthchecks, dependencies | Compose v2 spec, `condition: service_healthy` |
| **Dockerfile** | Host build context | Build sr-main image from .deb + ADBC drivers + .db files + entrypoint | Multi-step: `FROM ubuntu:24.04`, install DEB, copy drivers |
| **init-{pg,mysql,flightsql}.sql** | Host, volume-mounted | TPC-H DDL + seed data for each backend | SQL dialect-specific, executed at container startup |

## Recommended Project Structure

```
adbc_verification/
├── docker/                          # Docker Compose environment
│   ├── Dockerfile                   # sr-main image (FE+BE from DEB)
│   ├── entrypoint.sh               # sr-main startup: FE→wait→BE→register→wait
│   ├── docker-compose.yml          # All services, network, healthchecks
│   ├── starrocks-fe_*.deb          # FE .deb (copied by ship script)
│   ├── starrocks-be_*.deb          # BE .deb (copied by ship script)
│   ├── drivers/                    # ADBC .so files (copied from host via dbc)
│   │   ├── libadbc_driver_flightsql.so
│   │   ├── libadbc_driver_postgresql.so
│   │   ├── libadbc_driver_mysql.so
│   │   ├── libadbc_driver_sqlite.so
│   │   └── libadbc_driver_duckdb.so
│   ├── init/                       # Backend initialization SQLs
│   │   ├── init-pg.sql             # TPC-H tables + data (PostgreSQL dialect)
│   │   ├── init-mysql.sql          # TPC-H tables + data (MySQL dialect)
│   │   └── init-flightsql.sql      # TPC-H tables + data (SQLite/flightsql dialect)
│   ├── data/                       # File-based backend data (built once)
│   │   ├── duckdb_tpch.db          # Pre-populated DuckDB with TPC-H
│   │   └── sqlite_tpch.db          # Pre-populated SQLite with TPC-H
│   └── generate_data.sh            # One-time: generate .db files + init SQLs
├── queries/                        # SQL query corpus (outside containers)
│   ├── tpch/                       # TPC-H benchmark queries
│   │   ├── q01.sql
│   │   ├── q02.sql
│   │   └── ...
│   └── cross_driver/               # Cross-driver join test queries
│       ├── pg_flightsql_join.sql
│       └── mysql_pg_join.sql
├── tests/                          # pytest test suite
│   ├── conftest.py                 # Adapted for Docker Compose service names
│   ├── test_sqlite.py
│   ├── test_duckdb.py
│   ├── test_mysql.py
│   ├── test_postgres.py
│   ├── test_flightsql.py
│   ├── test_cross_join.py
│   └── test_negative.py
├── lib/                            # Shared library code
│   ├── catalog_helpers.py          # CREATE/DROP CATALOG (unchanged)
│   ├── docker_backends.py          # → REPLACED by docker-compose.yml
│   └── starrocks.py                # → REPLACED by Docker Compose startup
├── scripts/                        # Orchestration scripts
│   ├── ship_and_test.sh            # Full cycle: copy DEB → up --build → test → report
│   └── fast_iterate.sh             # Fast path: up -d --build → subset tests
└── pyproject.toml
```

### Structure Rationale

- **`docker/`**: Self-contained Docker Compose environment. Everything needed to build/run lives here. DEB files copied in (not symlinked) so the `build` context is portable.
- **`docker/init/`**: One SQL file per backend. PostgreSQL and MySQL have dialect differences (e.g., `INTEGER PRIMARY KEY` vs `INT AUTO_INCREMENT PRIMARY KEY`), so they can't share a single file. SQLite/flightsql uses its own dialect.
- **`docker/data/`**: Pre-built database files for embedded backends (DuckDB, SQLite). Generated once by `generate_data.sh` and checked in (or built on first use). These are `.db` files — not SQL — because DuckDB/SQLite ADBC drivers open live database files, not connection strings.
- **`queries/`**: Outside `docker/` because queries are the test corpus — they change independently of the deployment environment. Mounted read-only into sr-main so the entrypoint can run smoke tests if desired, but primarily read by pytest and sent via MySQL protocol.
- **`scripts/`**: Orchestration scripts that tie the pieces together. Separated from tests because they're the CI/local dev loop entry points, not test logic.
- **`lib/docker_backends.py` and `lib/starrocks.py`**: Replaced entirely. Docker Compose handles container lifecycle (no more subprocess `docker run` calls). StarRocks startup moves into `entrypoint.sh`. These files become dead code — schedule for removal in the transition phase.

## Architectural Patterns

### Pattern 1: FE+BE Co-location in Single Container

**What:** The StarRocks frontend (FE) and backend (BE) processes run inside the same container, started sequentially by an entrypoint script.

**When to use:** Development verification environments where simplicity trumps production-grade separation. The rtv reference architecture proves this works.

**Trade-offs:**
- **Pros**: Single Dockerfile, single healthcheck, no need for FE-to-BE network configuration across containers, matches the shipped DEB structure (DEBs install both fe/be under `/usr/lib/starrocks/`).
- **Cons**: Can't scale BE independently, container restart restarts both, log interleaving. Not representative of production (multi-node) deployment.

**Example** (from rtv reference — adopted pattern):
```bash
#!/bin/bash
# entrypoint.sh — sequential startup inside sr-main
# 1. Clean stale PID files
rm -f /usr/lib/starrocks/fe/bin/fe.pid /var/lib/starrocks/fe/meta/lock

# 2. Patch priority_networks with container IP at runtime
CONTAINER_IP=$(hostname -i | awk '{print $1}')
CONTAINER_SUBNET=$(echo "$CONTAINER_IP" | sed 's/\.[0-9]*$/.0\/24/')
echo "priority_networks = $CONTAINER_SUBNET" >> /etc/starrocks/fe/fe.conf
echo "priority_networks = $CONTAINER_SUBNET" >> /etc/starrocks/be/be.conf

# 3. Start FE, wait for MySQL port 9030
/usr/lib/starrocks/fe/bin/start_fe.sh --daemon
# ... wait loop with nc -z 127.0.0.1 9030 ...

# 4. Start BE, wait for heartbeat port 9060
/usr/lib/starrocks/be/bin/start_be.sh --daemon
# ... wait loop ...

# 5. Register BE with FE
mysql -uroot -h127.0.0.1 -P9030 -e \
  "ALTER SYSTEM ADD BACKEND '${CONTAINER_IP}:9050';"
# ... wait until SHOW BACKENDS shows Alive=true ...

# 6. Run init scripts if mounted
# 7. Keep container alive: tail -f fe.log
exec tail -f /var/log/starrocks/fe/fe.log
```

### Pattern 2: Docker Network DNS for Backend Discovery (Not Host Ports)

**What:** Backend containers are addressed by their Compose service name (DNS resolution on the bridge network), not by `localhost:{exposed_port}`. Host ports are only published for the MySQL protocol port that pytest needs.

**When to use:** Multi-container test environments. The rtv reference uses this pattern: `rtv-pg1` as the PostgreSQL hostname from inside `rtv-main`.

**Trade-offs:**
- **Pros**: No port conflicts (containers use their native ports internally), deterministic addressing (service name == hostname), no `localhost` confusion, matches how StarRocks would address remote backends.
- **Cons**: Service names become implicit coupling (must match between docker-compose.yml and conftest.py). Backend containers can't be accessed directly from host for debugging (need `docker compose exec`).

**Example** (how conftest.py references backends):
```python
# conftest.py — configure via env vars, default to service names
import os

# Docker network service names (resolved by Docker DNS inside sr-main)
PG_HOST = os.environ.get("PG_HOST", "sr-pg")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "sr-mysql")
FLIGHTSQL_HOST = os.environ.get("FLIGHTSQL_HOST", "sr-flightsql")

# Driver paths INSIDE the sr-main container (not host paths)
FLIGHTSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_flightsql.so"
POSTGRESQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_postgresql.so"
MYSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
SQLITE_DRIVER = "/opt/starrocks/drivers/libadbc_driver_sqlite.so"
DUCKDB_DRIVER = "/opt/starrocks/drivers/libadbc_driver_duckdb.so"

# File-based database paths inside sr-main
SQLITE_DB_PATH = "/opt/starrocks/data/sqlite_tpch.db"
DUCKDB_DB_PATH = "/opt/starrocks/data/duckdb_tpch.db"

# StarRocks connection (host connects to published port)
STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))
```

### Pattern 3: Healthcheck-Gated Service Dependencies

**What:** `depends_on` with `condition: service_healthy` ensures StarRocks doesn't start until backends are ready, and tests don't run until StarRocks is healthy.

**When to use:** Any multi-service Docker Compose environment with startup ordering requirements. Standard Docker Compose pattern (Compose v2.1+ file format or v3 with `depends_on` `condition` support).

**Trade-offs:**
- **Pros**: Deterministic startup order, no flaky "backend not ready" errors, pytest can assume everything is up when it runs.
- **Cons**: Adds startup time (each healthcheck poll cycle). `start_period` must be tuned per backend — too short causes false negatives, too long wastes time.

**Example:**
```yaml
services:
  sr-pg:
    image: postgres:16
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pguser -d tpch"]
      interval: 3s
      timeout: 3s
      retries: 10
      start_period: 10s

  sr-mysql:
    image: mysql:8.0
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-uroot", "-ptestpass", "--silent"]
      interval: 5s
      timeout: 3s
      retries: 15
      start_period: 30s

  sr-flightsql:
    image: voltrondata/sqlflite:latest
    healthcheck:
      test: ["CMD", "grpc_health_probe", "-addr=:31337"]
      interval: 5s
      timeout: 3s
      retries: 15
      start_period: 15s

  sr-main:
    build: .
    depends_on:
      sr-pg:
        condition: service_healthy
      sr-mysql:
        condition: service_healthy
      sr-flightsql:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "mysql", "-uroot", "-h127.0.0.1", "-P9030", "-e", "SELECT 1"]
      interval: 5s
      timeout: 3s
      retries: 30
      start_period: 40s
```

### Pattern 4: Host as Test Runner (Not pytest-in-docker)

**What:** pytest runs on the host machine, connecting to the StarRocks MySQL port published at `127.0.0.1:9030`. Test code and query files live on the host filesystem.

**When to use:** When test iteration speed matters, and you want to edit tests/queries without rebuilding container images. The rtv reference uses this exact pattern.

**Trade-offs:**
- **Pros**: Fast iteration (edit test → rerun, no rebuild), rich IDE integration, pytest plugins work normally, debug with `pdb` directly, no need for Docker-in-Docker.
- **Cons**: Requires Python + pymysql on host (already true), MySQL port must be published, can't test "from inside the network" without extra setup.

**Why not pytest-in-docker**: The StarRocks container would need Python and the test suite baked in, increasing image size and build time. Every test change would require a rebuild. The rtv reference avoids this, and so should we.

## Data Flow

### Primary Query Flow (host → StarRocks → backend → host)

```
pytest (host)                              sr-main (Docker)                    sr-pg (Docker)
     │                                           │                                  │
     │  1. pymysql: "CREATE EXTERNAL CATALOG     │                                  │
     │     sr_pg PROPERTIES(driver_url=...,      │                                  │
     │     uri=postgresql://sr-pg:5432/...)"     │                                  │
     ├──────────────────────────────────────────►│                                  │
     │                                           │  2. BE loads libadbc_driver_    │
     │                                           │     postgresql.so, connects      │
     │                                           ├─────────────────────────────────►│
     │                                           │  3. PostgreSQL returns schema    │
     │                                           │     metadata via Arrow Flight    │
     │                                           │◄─────────────────────────────────┤
     │  4. Catalog created (OK)                  │                                  │
     │◄──────────────────────────────────────────┤                                  │
     │                                           │                                  │
     │  5. Read query from queries/tpch/q03.sql  │                                  │
     │     → send via pymysql:                    │                                  │
     │     "SELECT * FROM sr_pg.tpch.region       │                                  │
     │      JOIN sr_mysql.tpch.nation            │                                  │
     │      ON r_regionkey = n_regionkey"        │                                  │
     ├──────────────────────────────────────────►│                                  │
     │                                           │  6. FE parses, plans distributed  │
     │                                           │     query, dispatches to BE      │
     │                                           │                                  │
     │                                           │  7. BE executes ADBC scan on     │
     │                                           │     sr-pg (region table)         │
     │                                           ├─────────────────────────────────►│
     │                                           │  8. PostgreSQL returns Arrow      │
     │                                           │     record batches               │
     │                                           │◄─────────────────────────────────┤
     │                                           │                                  │
     │                                           │  9. BE executes ADBC scan on     │
     │                                           │     sr-mysql (nation table)      │
     │                                           ├─────────────────────────────────►│
     │                                           │     (sr-mysql:3306)              │
     │                                           │                                  │
     │  10. Result set (MySQL wire protocol)     │                                  │
     │◄──────────────────────────────────────────┤                                  │
     │                                           │                                  │
     │  11. pytest assert on result              │                                  │
```

### Startup Flow (docker compose up --build)

```
docker compose up --build
    │
    ├─► 1. Build sr-main image (Dockerfile)
    │      ├ Copy DEB files → dpkg -i
    │      ├ Copy ADBC drivers → /opt/starrocks/drivers/
    │      ├ Copy DuckDB/SQLite .db → /opt/starrocks/data/
    │      └ Copy entrypoint.sh → /
    │
    ├─► 2. Start backend containers (in parallel)
    │      ├ sr-pg: postgres:16 starts, mounts init-pg.sql
    │      │   └ PostgreSQL executes init-pg.sql → TPC-H tables seeded
    │      ├ sr-mysql: mysql:8.0 starts, mounts init-mysql.sql
    │      │   └ MySQL executes init-mysql.sql → TPC-H tables seeded
    │      └ sr-flightsql: sqlflite starts, mounts init-flightsql.sql
    │          └ sqlflite executes init SQL → TPC-H tables seeded
    │
    ├─► 3. Healthchecks poll until each backend is ready
    │      └ depends_on condition: service_healthy gates sr-main start
    │
    ├─► 4. Start sr-main
    │      └ entrypoint.sh:
    │         ├ Clean stale PID files
    │         ├ Patch priority_networks with container IP
    │         ├ Start FE (wait for port 9030)
    │         ├ Start BE (wait for port 9060)
    │         ├ Register BE with FE (ALTER SYSTEM ADD BACKEND)
    │         └ Wait until BE shows Alive=true
    │
    └─► 5. docker compose up --wait returns (all services healthy)
         └ pytest can now connect to 127.0.0.1:9030
```

### Ship→Verify→Retest Loop

```
┌──────────────────────────────────────────────────────────┐
│  1. BUILD: StarRocks repo ./build.sh --fe --be           │
│     └ Output: output/fe/, output/be/                     │
│                                                          │
│  2. PACKAGE: cd packaging/debian && ./build.sh           │
│     └ Output: starrocks-fe_*.deb, starrocks-be_*.deb     │
│                                                          │
│  3. SHIP: cp *.deb → adbc_verification/docker/           │
│                                                          │
│  4. VERIFY: cd docker && docker compose up -d --build    │
│     └ Wait for healthchecks (docker compose up --wait)   │
│                                                          │
│  5. TEST: cd .. && .venv/bin/pytest tests/ -v            │
│     ├ pytest connects to 127.0.0.1:9030                  │
│     ├ Creates catalogs for each backend                  │
│     ├ Runs TPC-H queries + cross-driver joins            │
│     └ Captures container logs on failure                 │
│                                                          │
│  6. REPORT: .venv/bin/pytest --json-report               │
│     └ Aggregate results, highlight failures              │
│                                                          │
│  7. (optional) TEARDOWN: docker compose down             │
│     └ Or leave running for next iteration                │
│                                                          │
│  8. FIX (if failed): edit code → goto 1                  │
└──────────────────────────────────────────────────────────┘
```

### Fast Iteration Path (no rebuild needed)

```
# Only if test code or queries changed (no StarRocks rebuild):
docker compose up -d         # reuse existing images, restart if needed
.venv/bin/pytest tests/test_flightsql.py -v  # run subset

# If StarRocks DEB changed:
cd docker && docker compose up -d --build    # rebuilds sr-main only
cd .. && .venv/bin/pytest tests/ -v

# If only backends need fresh data:
docker compose up -d --force-recreate sr-pg sr-mysql sr-flightsql
```

### Log Capture on Failure

```
pytest test failure →
  ┌─ capture_on_failure fixture (autouse)
  │   ├ docker compose logs sr-main     → FE log tail
  │   ├ docker compose logs sr-main     → BE log tail
  │   ├ docker compose logs sr-pg       → PostgreSQL log tail
  │   ├ docker compose logs sr-mysql    → MySQL error log tail
  │   └ docker compose logs sr-flightsql → sqlflite query log
  └─ Append to test report (--json-report or terminal output)
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **1 developer, local** | Current architecture. Single Docker Compose stack on one machine. ~4 containers total. Bridge network. |
| **CI (single pipeline)** | Same architecture. Add `docker compose up --wait --wait-timeout 120` for CI auto-wait. `docker compose down -v` for cleanup. |
| **CI (matrix builds)** | Parallel pytest runs would need unique project names (`COMPOSE_PROJECT_NAME` per matrix cell) to avoid container name collisions. |
| **Multi-version testing** | Parameterize the DEB source (not the Dockerfile). The ship script copies the right DEB version. Dockerfile stays generic. |

### Scaling Priorities

1. **First bottleneck**: StarRocks startup time (~60-90s for FE+BE). Mitigation: keep sr-main running across test iterations (don't down/up unless DEB changed).
2. **Second bottleneck**: Backend data seeding (init SQL execution). Mitigation: pre-seeded images or volume persistence for backend data.
3. **Not a bottleneck for the scale**: Network throughput (all local), concurrency (single pytest process), container count (4-5).

## Anti-Patterns

### Anti-Pattern 1: Host Ports for Backend-to-StarRocks Communication

**What people do:** Publish every backend port to the host, then have StarRocks catalogs point to `host.docker.internal:{port}` or use `--network host`.

**Why it's wrong:** Bypasses Docker DNS service discovery. Creates port conflicts (PostgreSQL on 5432, MySQL on 3306 — can't run multiple instances or conflicts with host services). `host.docker.internal` doesn't exist on Linux without extra config. Tightly couples the test environment to the host machine.

**Do this instead:** Use Docker internal bridge network. Backend containers are addressed by service name (e.g., `sr-pg:5432`). Only publish the MySQL port that pytest needs. This is the rtv reference pattern and it works reliably.

### Anti-Pattern 2: Separate FE and BE Containers for Verification

**What people do:** Model the production topology: one FE container, one BE container, separate services in docker-compose.yml.

**Why it's wrong:** Adds complexity (inter-container FE-BE communication, dual healthchecks, priority_network configuration across containers) without adding testing value. The test suite doesn't verify distributed deployment — it verifies ADBC catalog functionality.

**Do this instead:** Co-locate FE+BE in a single container, started sequentially by entrypoint.sh. This is the rtv reference pattern. If distributed verification is needed later, it's a separate project concern.

### Anti-Pattern 3: pytest Inside Docker

**What people do:** Build a second Docker image with Python + test suite, run as a Compose service.

**Why it's wrong:** Every test change requires a rebuild. Debugging requires `docker exec` or volume hacks. pytest plugins, IDE integration, and `pdb` break. Slows the inner dev loop dramatically.

**Do this instead:** Keep pytest on the host. Connect to the published MySQL port. Edit tests, rerun instantly. This is the rtv reference pattern.

### Anti-Pattern 4: Volume-Mounted ADBC Drivers (Instead of Baked Into Image)

**What people do:** Mount host ADBC driver `.so` files into the container at runtime via `volumes:`.

**Why it's wrong:** Host paths are machine-specific (breaks portability). Driver version mismatches between host and container libraries. Volume mounts with `:ro` prevent driver updates in the container.

**Do this instead:** Copy ADBC driver `.so` files into the Docker build context (`docker/drivers/`) and `COPY` them into the image during `docker build`. The drivers become part of the immutable image. This is the rtv reference pattern.

### Anti-Pattern 5: SQL Queries Baked Into Python Test Files

**What people do:** Embed TPC-H queries as Python string literals inside test functions.

**Why it's wrong:** Hard to review SQL in Python strings. Can't run queries independently (e.g., via `mysql` CLI for debugging). Formatting/escaping issues. Can't share queries across test runners or tools.

**Do this instead:** External SQL query corpus in `queries/` directory. Tests read SQL from files and substitute parameters as needed. Queries are versionable, reviewable, and runnable independently.

## Integration Points

### External to This Project

| Interface | Integration Pattern | Notes |
|-----------|---------------------|-------|
| **StarRocks .deb** | Copied into `docker/` by ship script | Source: StarRocks repo build output. `docker/starrocks-fe_*.deb` and `docker/starrocks-be_*.deb` |
| **ADBC drivers** | Copied into `docker/drivers/` | Source: `~/.config/adbc/drivers/*.toml` (resolved to .so paths) or `dbc install` output |
| **Docker Engine** | Docker socket access for `docker compose` commands | Host must have Docker + Compose v2 |
| **Python environment** | `.venv/` with pytest, pymysql | Already set up; no changes needed |

### Internal Boundaries

| Boundary | Communication | Protocol | Notes |
|----------|---------------|----------|-------|
| **pytest → sr-main** | Host `127.0.0.1:9030` | MySQL wire protocol (pymysql) | Published port; only host-to-container boundary |
| **sr-main → sr-pg** | Docker network `sr-pg:5432` | ADBC PostgreSQL (Arrow Flight) | Container-to-container, internal network |
| **sr-main → sr-mysql** | Docker network `sr-mysql:3306` | ADBC MySQL (Arrow Flight) | Container-to-container, internal network |
| **sr-main → sr-flightsql** | Docker network `sr-flightsql:31337` | ADBC FlightSQL (gRPC Arrow Flight) | Container-to-container, internal network |
| **sr-main → DuckDB .db** | Local filesystem `/opt/starrocks/data/` | ADBC DuckDB (in-process) | File access inside container |
| **sr-main → SQLite .db** | Local filesystem `/opt/starrocks/data/` | ADBC SQLite (in-process) | File access inside container |
| **host → sr-main logs** | `docker compose logs sr-main` | Docker API | Used by capture_on_failure fixture |
| **host → queries/** | Local filesystem read | File I/O | pytest reads query files, sends SQL via pymysql |

### Critical Configuration Values

| Config Key | Where Set | Value | Purpose |
|------------|-----------|-------|---------|
| `priority_networks` | entrypoint.sh | `{container_ip}/24` | StarRocks binds to Docker bridge subnet |
| `driver_url` | conftest.py → CREATE CATALOG | `/opt/starrocks/drivers/libadbc_driver_{type}.so` | Path INSIDE sr-main container |
| `uri` | conftest.py → CREATE CATALOG | `{protocol}://{service_name}:{port}/{db}...` | Backend connection string using Docker DNS names |
| `POSTGRES_USER/PASSWORD/DB` | docker-compose.yml | `pguser` / `pgpass` / `tpch` | PostgreSQL credentials |
| `MYSQL_ROOT_PASSWORD/MYSQL_DATABASE` | docker-compose.yml | `testpass` / `tpch` | MySQL credentials |
| `STARROCKS_HOST/PORT` | conftest.py (env var) | `127.0.0.1` / `9030` | Where pytest connects |

## Sources

- **[GSD Project](https://github.com/vercel/gsd)**: Standard project structure (internal tooling docs site)
- **remote_table_verification** (`/home/mete/coding/remote_table_verification/`): Proven reference architecture — Docker Compose with FE+BE co-located, ADBC drivers in image, host pytest, Docker network DNS. HIGH confidence.
- **Docker Compose specification** (https://docs.docker.com/compose/compose-file/): Service definitions, healthchecks, depends_on, networks, volumes. Context7-verified. HIGH confidence.
- **PostgreSQL Docker image** (https://hub.docker.com/_/postgres): `docker-entrypoint-initdb.d/` init script pattern. Official Docker Hub docs. HIGH confidence.
- **MySQL Docker image** (https://hub.docker.com/_/mysql): `docker-entrypoint-initdb.d/` init script pattern. Official Docker Hub docs. HIGH confidence.
- **StarRocks DEB packaging**: DEB installs to `/usr/lib/starrocks/`, conf to `/etc/starrocks/`, logs to `/var/log/starrocks/`. Confirmed from rtv Dockerfile. HIGH confidence.
- **ADBC driver loading**: StarRocks BE loads ADBC drivers from `driver_url` property in CREATE EXTERNAL CATALOG. Path must be accessible inside the container. Confirmed from existing test suite. HIGH confidence.

---

*Architecture research for: Docker Compose-based StarRocks ADBC verification suite*
*Researched: 2026-04-27*
