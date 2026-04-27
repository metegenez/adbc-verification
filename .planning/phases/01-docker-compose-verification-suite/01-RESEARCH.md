# Phase 1: Docker Compose Verification Suite — Research

**Researched:** 2026-04-27
**Status:** Complete

## Architecture Decision Summary

**Approach:** Docker Compose orchestration of StarRocks (from shipped `.deb` with baked-in ADBC drivers) + backend data services on a bridge network, pytest from host → single published MySQL port. Direct adaptation of the proven `remote_table_verification` pattern extended to all 5 ADBC drivers, TPC-H data, and CLI tooling.

**Key insight:** The reference project at `/home/mete/coding/remote_table_verification/` provides ~70% of the Dockerfile, docker-compose.yml, and entrypoint script — these are adapted with driver baking added and additional backend services.

---

## 1. StarRocks Containerization (DC-02, DC-03)

### Base Image & Dependencies
- **Base:** `ubuntu:24.04` (same as reference project — proven compatibility with SR .debs)
- **JDK:** `openjdk-17-jre-headless` (FE requires JDK 17)
- **Tools:** `mysql-client` (healthcheck + init SQL), `netcat-openbsd` (port probes), `curl` (optional)
- **No multi-stage build needed** — single-stage, final size ~2-3GB with JRE + SR binaries + drivers

### StarRocks DEB Installation
- FE `.deb` installs to `/usr/lib/starrocks/fe/` with config at `/etc/starrocks/fe/fe.conf`
- BE `.deb` installs to `/usr/lib/starrocks/be/` with config at `/etc/starrocks/be/be.conf`
- Logs at `/var/log/starrocks/fe/fe.log` and `/var/log/starrocks/be/be.INFO`
- PID files at `/usr/lib/starrocks/fe/bin/fe.pid` and `/usr/lib/starrocks/be/bin/be.pid`
- Start scripts: `/usr/lib/starrocks/fe/bin/start_fe.sh --daemon`, `/usr/lib/starrocks/be/bin/start_be.sh --daemon`
- **CRITICAL:** Both install paths confirmed from reference project Dockerfile (`dpkg -i`)

### Dockerfile Pattern (adapted from reference)
```dockerfile
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless mysql-client netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

COPY starrocks-fe_*.deb starrocks-be_*.deb /tmp/
RUN dpkg -i /tmp/starrocks-fe_*.deb /tmp/starrocks-be_*.deb && rm /tmp/*.deb

# Additional config — Arrow Flight ports for all backend comms
RUN echo "arrow_flight_port = 9408" >> /etc/starrocks/fe/fe.conf && \
    echo "arrow_flight_port = 9419" >> /etc/starrocks/be/be.conf

COPY drivers/ /opt/starrocks/drivers/
COPY data/ /opt/starrocks/data/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 9030 8030 9408 9050 9419
ENTRYPOINT ["/entrypoint.sh"]
```

### Entrypoint Script Pattern
1. Clean stale PID/lock files
2. Detect container IP → `hostname -i | awk '{print $1}'`
3. Patch `priority_networks = {CONTAINER_SUBNET}` into both fe.conf and be.conf
4. Start FE daemon, poll `nc -z 127.0.0.1 9030` up to 120s
5. Start BE daemon, poll `nc -z 127.0.0.1 9060` up to 60s
6. Register BE: `ALTER SYSTEM ADD BACKEND '{IP}:9050'`
7. Poll `SHOW PROC '/backends'` until alive
8. Run `/docker-entrypoint-initdb.d/*.sql` init scripts (for StarRocks-internal seed data if needed)
9. `exec tail -f /var/log/starrocks/fe/fe.log` to keep container alive

**Entrypoint timeout targets:**
- FE port open: 90s (Docker Compose start_period + retries give ~150s)
- BE port open: 60s
- BE registration: 60s

**Edge cases:**
- Patching priority_networks with `/24` subnet from container IP — confirmed working in reference
- BE registration may fail if FE isn't fully initialized even though port 9030 is open — the `SHOW PROC` poll handles this
- `ALTER SYSTEM ADD BACKEND` may fail if BE was already registered from a previous run — `|| true` in reference, but we should use a cleaner approach (check first, or `ADD BACKEND` is idempotent)

### Healthcheck
```yaml
healthcheck:
  test: ["CMD", "mysql", "-uroot", "-h127.0.0.1", "-P9030", "-e", "SELECT 1"]
  interval: 5s
  timeout: 3s
  retries: 60
  start_period: 60s
```
This gives ~360s total for full FE+BE startup. FE alone starts in ~30s; BE registration takes 10-30s after.

---

## 2. ADBC Driver Strategy (DC-02, DC-03)

### Driver Files (5 total)
| Driver | File Name | Source | Container Path |
|--------|-----------|--------|----------------|
| SQLite | `libadbc_driver_sqlite.so` | `~/.config/adbc/drivers/sqlite.toml` → host path | `/opt/starrocks/drivers/libadbc_driver_sqlite.so` |
| PostgreSQL | `libadbc_driver_postgresql.so` | `~/.config/adbc/drivers/postgresql.toml` → host path | `/opt/starrocks/drivers/libadbc_driver_postgresql.so` |
| FlightSQL | `libadbc_driver_flightsql.so` | `~/.config/adbc/drivers/flightsql.toml` → host path | `/opt/starrocks/drivers/libadbc_driver_flightsql.so` |
| DuckDB | `libadbc_driver_duckdb.so` | `~/.config/adbc/drivers/duckdb.toml` → host path | `/opt/starrocks/drivers/libadbc_driver_duckdb.so` |
| MySQL | `libadbc_driver_mysql.so` | `~/.config/adbc/drivers/mysql.toml` → host path | `/opt/starrocks/drivers/libadbc_driver_mysql.so` |

### Driver Discovery at Build Time
The existing `lib/driver_registry.py` reads TOML manifests from `~/.config/adbc/drivers/` to find host `.so` paths. This is still useful at **build time** (Dockerfile COPY needs source paths). Options:

1. **Pre-copy to `docker/drivers/`:** User runs `python -m lib.driver_registry --copy-to docker/drivers/` once → Dockerfile does `COPY docker/drivers/ /opt/starrocks/drivers/`
2. **Dockerfile RUN with TOML resolution:** Copy TOML files into build context, resolve paths in Dockerfile — fragile (host paths may not be in build context)
3. **Build script wrapper:** `setup-drivers.sh` that copies .so files from TOML-resolved paths to `docker/drivers/` before `docker compose build`

**Recommendation: Option 1 (pre-copy)** — simplest, Dockerfile just copies a flat directory. The `lib/driver_registry.py` provides a `get_all_driver_paths()` function that returns `{name: path}`. A small script or make target copies those files.

### Runtime Path Resolution
At runtime (inside StarRocks container), driver paths are fixed constants:
```python
SQLITE_DRIVER = "/opt/starrocks/drivers/libadbc_driver_sqlite.so"
POSTGRES_DRIVER = "/opt/starrocks/drivers/libadbc_driver_postgresql.so"
FLIGHTSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_flightsql.so"
DUCKDB_DRIVER = "/opt/starrocks/drivers/libadbc_driver_duckdb.so"
MYSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
```

Conftest driver path fixtures become simple constants (no TOML parsing at runtime). The `lib/driver_registry.py` module is still used at build time only.

### SQLite/DuckDB Data Files (DC-03)
Pre-baked `.db` files copied into the StarRocks image:
```
COPY docker/data/ /opt/starrocks/data/
```
Expected files:
- `/opt/starrocks/data/tpch_sqlite.db` — TPC-H schema + data for SQLite
- `/opt/starrocks/data/tpch_duckdb.db` — TPC-H schema + data for DuckDB
- `/opt/starrocks/data/test_sqlite.db` — simple test data for basic lifecycle tests
- `/opt/starrocks/data/cross_sqlite_a.db`, `/opt/starrocks/data/cross_sqlite_b.db` — cross-join test databases

These are generated at build time via Python scripts (duckdb/sqlite3 packages in host .venv).

---

## 3. Backend Data Services (DC-03, DC-05)

### Service Definitions

#### PostgreSQL (sr-postgres)
```yaml
sr-postgres:
  image: postgres:16
  container_name: sr-postgres
  environment:
    POSTGRES_USER: testuser
    POSTGRES_PASSWORD: testpass
    POSTGRES_DB: testdb
  volumes:
    - ./init/postgres/:/docker-entrypoint-initdb.d/:ro
  networks:
    - sr-net
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U testuser -d testdb"]
    interval: 3s
    timeout: 3s
    retries: 20
```

#### MySQL (sr-mysql)
```yaml
sr-mysql:
  image: mysql:8.0
  container_name: sr-mysql
  environment:
    MYSQL_ROOT_PASSWORD: testpass
    MYSQL_DATABASE: testdb
  volumes:
    - ./init/mysql/:/docker-entrypoint-initdb.d/:ro
  networks:
    - sr-net
  healthcheck:
    test: ["CMD", "mysqladmin", "ping", "-uroot", "-ptestpass", "--silent"]
    interval: 5s
    timeout: 3s
    retries: 20
    start_period: 15s
```

#### FlightSQL/sqlflite (sr-flightsql)
```yaml
sr-flightsql:
  image: voltrondata/sqlflite:latest
  container_name: sr-flightsql
  environment:
    TLS_ENABLED: "0"
    SQLFLITE_PASSWORD: sqlflite_password
    PRINT_QUERIES: "1"
  volumes:
    - ./init/sqlflite/:/docker-entrypoint-initdb.d/:ro
  networks:
    - sr-net
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "31337"]
    interval: 3s
    timeout: 3s
    retries: 10
    start_period: 5s
```

#### FlightSQL/sqlflite with TLS (sr-flightsql-tls)
Separate service because TLS changing requires different container config:
```yaml
sr-flightsql-tls:
  image: voltrondata/sqlflite:latest
  container_name: sr-flightsql-tls
  environment:
    TLS_ENABLED: "1"
    SQLFLITE_PASSWORD: sqlflite_password
    PRINT_QUERIES: "1"
  volumes:
    - ./init/sqlflite/:/docker-entrypoint-initdb.d/:ro
  networks:
    - sr-net
  healthcheck:
    test: ["CMD", "nc", "-z", "127.0.0.1", "31337"]
    interval: 3s
    timeout: 5s
    retries: 15
    start_period: 10s
```
**Note:** sqlflite with TLS takes longer to start (cert generation + gRPC TLS init). The existing `lib/tls.py` had a 10s sleep after port open — the healthcheck retries + start_period handle this more robustly.

### Docker Network
```yaml
networks:
  sr-net:
    driver: bridge
```
All services communicate via Docker DNS service names: `sr-main`, `sr-postgres`, `sr-mysql`, `sr-flightsql`, `sr-flightsql-tls`.

### Init SQL Strategy
Each backend gets its own init directory:
```
docker/init/
  postgres/
    01-tpch-schema.sql     — TPC-H DDL (region, nation, orders, lineitem)
    02-tpch-data.sql       — TPC-H seed data (SF1 subset)
    03-test-data.sql        — Simple test_data table for lifecycle tests
  mysql/
    01-tpch-schema.sql     — TPC-H DDL (MySQL syntax)
    02-tpch-data.sql       — TPC-H seed data
    03-test-data.sql        — Simple test_data table
    04-cross-join.sql       — Departments table for cross-join tests
  sqlflite/
    (empty or N/A — sqlflite uses in-memory SQLite at startup;
     TPC-H data loaded via separate mechanism or pre-attached .db)
```

**PostgreSQL init:** Files in `/docker-entrypoint-initdb.d/` are executed alphabetically. Postgres official image runs them as the POSTGRES_USER.

**MySQL init:** Files in `/docker-entrypoint-initdb.d/` (`.sql`, `.sql.gz`, `.sh`) are executed at first-run init only. MySQL 8.0 image.

**FlightSQL/sqlflite:** This image does NOT support `/docker-entrypoint-initdb.d/` out of the box. It starts with an in-memory SQLite backend. Options:
1. Mount a pre-built `.db` file and configure sqlflite to use it
2. Accept that sqlflite starts empty and run setup SQL via the FlightSQL client after startup
3. Build a custom Dockerfile based on sqlflite that adds init SQL execution

**Recommendation:** Use pre-built `.db` files for sqlflite (mounted as volumes), since we already generate SQLite `.db` files for the StarRocks-baked SQLite driver. This keeps data generation centralized.

### TLS Certificate Handling

**FlightSQL TLS:** The sqlflite container generates self-signed certs internally at startup (at `/opt/sqlflite/tls/`). The CA cert (`root-ca.pem`) must be extracted to the host for pytest to reference.

**Options for cert extraction:**
1. **Docker Compose volume:** Mount a host directory to `/opt/sqlflite/tls/` — BUT this overwrites container-generated certs and breaks cert generation (known pitfall from `lib/tls.py`)
2. **`docker cp` approach:** After container is healthy, `docker cp sr-flightsql-tls:/opt/sqlflite/tls/root-ca.pem ./docker/certs/` — reliable but adds a step
3. **Pre-generated certs:** Generate certs on host, mount as read-only to sqlflite — requires understanding sqlflite's TLS cert expectations
4. **Custom entrypoint wrapper:** A wrapper script that starts sqlflite, waits for cert generation, copies certs to a shared volume

**Recommendation:** Use pre-generated self-signed certs. Generate once (`openssl req -new -x509 -days 365 -nodes -out root-ca.pem -keyout root-ca.key -subj '/CN=localhost'`), mount `root-ca.pem` and `root-ca.key` into the sqlflite TLS container. This is the same approach used for PostgreSQL TLS in the existing suite — consistent, reliable, no runtime extraction needed.

**PostgreSQL TLS:** Already handled in existing `test_postgres.py` — generates certs via `docker exec`, extracts server cert. For Compose: pre-generate certs, mount into PostgreSQL container, configure `postgresql.conf` for SSL. Same pattern as FlightSQL TLS.

### PostgreSQL DECIMAL→DOUBLE Issue (DC-05)
From ROADMAP plan 01-02: "PostgreSQL DECIMAL→DOUBLE cast resolution". This is a known ADBC driver behavior where PostgreSQL DECIMAL columns may be reported as DOUBLE by the driver. The resolution is to use explicit casts in query files or document the behavior. No Docker/Compose-specific fix needed — this is a test assertion concern.

---

## 4. Conftest Refactoring (DC-04)

### What Changes

| Current | New |
|---------|-----|
| `ensure_starrocks_running()` starts FE/BE via subprocess | `sr_conn` fixture connects to `STARROCKS_HOST:STARROCKS_PORT` |
| `STARROCKS_HOME` env var | `STARROCKS_HOST` (default: `127.0.0.1`), `STARROCKS_PORT` (default: `9030`) |
| `get_driver_path("sqlite")` reads TOML | Driver paths are module-level constants (`/opt/starrocks/drivers/...`) |
| `mysql_port()` starts Docker container | `mysql_port()` returns 3306 (service name used for URIs, ports are internal) |
| `postgres_port()` starts Docker container | `postgres_port()` returns 5432 (same pattern) |
| `sqlflite_port()` starts Docker container | `sqlflite_port()` returns 31337 |
| `sqlflite_tls()` starts TLS container, extracts cert | `sqlflite_tls()` returns `(31337, ca_cert_path)` with pre-generated cert path |
| `capture_on_failure()` reads log files | `capture_on_failure()` runs `docker compose logs --tail=50` |
| `ensure_flightsql_running()` etc. | Retired entirely |

### New Conftest Structure
```python
import os
import subprocess

STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))

# Container-internal driver paths (baked into StarRocks image)
SQLITE_DRIVER = "/opt/starrocks/drivers/libadbc_driver_sqlite.so"
POSTGRES_DRIVER = "/opt/starrocks/drivers/libadbc_driver_postgresql.so"
FLIGHTSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_flightsql.so"
DUCKDB_DRIVER = "/opt/starrocks/drivers/libadbc_driver_duckdb.so"
MYSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"

# Docker network service names (from docker-compose.yml)
SR_MAIN = "sr-main"
SR_POSTGRES = "sr-postgres"
SR_MYSQL = "sr-mysql"
SR_FLIGHTSQL = "sr-flightsql"
SR_FLIGHTSQL_TLS = "sr-flightsql-tls"

# TLS cert paths (pre-generated, mounted as volumes)
FLIGHTSQL_CA_CERT = os.environ.get(
    "FLIGHTSQL_CA_CERT",
    "docker/certs/flightsql-ca.pem"
)
POSTGRES_CA_CERT = os.environ.get(
    "POSTGRES_CA_CERT",
    "docker/certs/postgres-ca.pem"
)

@pytest.fixture(scope="session")
def sr_conn():
    conn = pymysql.connect(
        host=STARROCKS_HOST,
        port=STARROCKS_PORT,
        user="root",
        password="",
        autocommit=True,
    )
    yield conn
    conn.close()

@pytest.fixture(scope="session")
def sqlite_driver_path() -> str:
    return SQLITE_DRIVER

# ... same pattern for other drivers ...

@pytest.fixture(scope="session")
def mysql_port() -> int:
    return 3306  # service-internal port

# capture_on_failure adapted:
@pytest.fixture(autouse=True)
def capture_on_failure(request):
    yield
    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is not None and rep_call.failed:
        try:
            logs = subprocess.run(
                ["docker", "compose", "logs", "--tail=50"],
                capture_output=True, text=True, timeout=10,
                cwd="docker/"
            )
            request.node.user_properties.append(
                ("compose_logs", logs.stdout[-5000:])
            )
        except Exception:
            pass
```

### What Gets Retired
| Retired File | Reason |
|-------------|--------|
| `lib/docker_backends.py` | Containers managed by docker compose, not subprocess |
| `lib/starrocks.py` (startup/log functions) | Replaced by docker compose healthchecks + `docker compose logs` |
| Module-level `subprocess.run(["sqlite3", ...])` data fixtures | Data pre-baked in images or init scripts |
| `docker exec` data seeding fixtures | Replaced by initdb.d scripts |
| `lib/tls.py` sqlflite TLS container start | Replaced by Compose service + pre-generated certs |

### What Stays
| File | Reason |
|------|--------|
| `lib/catalog_helpers.py` | Pure SQL functions, agnostic to container topology |
| `lib/driver_registry.py` | Still used at build time for .so file discovery |
| `pyproject.toml` | Dependencies and pytest markers unchanged |
| All `tests/test_*.py` business logic | Only URIs and driver paths change |

### URI Pattern Changes
Tests currently use `127.0.0.1:{dynamic_port}`. After refactoring, backends use Docker service names:
```python
# PostgreSQL — was: postgresql://testuser:testpass@127.0.0.1:5432/testdb
# Now: postgresql://testuser:testpass@sr-postgres:5432/testdb
# (StarRocks BE connects; service name resolved via Docker DNS)

# MySQL — was: mysql://root:testpass@127.0.0.1:3306/testdb
# Now: mysql://root:testpass@sr-mysql:3306/testdb

# FlightSQL — was: grpc://127.0.0.1:31337
# Now: grpc://sr-flightsql:31337

# FlightSQL TLS — was: grpc+tls://127.0.0.1:31338
# Now: grpc+tls://sr-flightsql-tls:31337
```

---

## 5. Test Module Adaptations

### Per-Module Changes

| Module | Changes |
|--------|---------|
| `test_sqlite.py` | Remove `subprocess.run(["sqlite3", ...])` fixtures → use pre-baked .db paths. `sqlite_test_db()` fixture returns fixed path like `/opt/starrocks/data/test_sqlite.db` |
| `test_duckdb.py` | Remove `duckdb` Python package dependency for data creation → use pre-baked .db. `duckdb_test_db()` returns `/opt/starrocks/data/tpch_duckdb.db` |
| `test_mysql.py` | Remove `docker exec mysql` seeding → data loaded via init scripts. Remove `mysql_test_data` fixture dependency (data always present). `_MYSQL_URI` changes to use service name |
| `test_postgres.py` | Remove `docker exec psql` seeding → data loaded via init scripts. `postgres_test_data` fixture becomes a no-op or health check. `_PG_URI` changes. TLS cert extraction → pre-generated cert path |
| `test_flightsql.py` | Remove `sqlflite_port`/`sqlflite_tls` Docker container start → Comes up via Compose. Port fixtures return static values. `sqlflite_tls` returns pre-generated cert path |
| `test_cross_join.py` | Remove `sqlite3` subprocess data creation → pre-baked cross-join .db files. Remove `docker exec psql` seeding → init scripts. `cross_sqlite_db()` returns fixed paths. `cross_postgres_data()` fixture removed |
| `test_negative.py` | Minimal changes — uses SQLite driver path only. Driver path fixture already returns constant |

### Data Generation for Pre-Baked Files
Create a Python script `docker/generate-data.py` that:
1. Creates SQLite TPC-H .db: `tpch_sqlite.db`
2. Creates DuckDB TPC-H .db: `tpch_duckdb.db`
3. Creates SQLite test databases: `test_sqlite.db`, `cross_sqlite_a.db`, `cross_sqlite_b.db`
4. Outputs to `docker/data/` directory

This script runs once (not per-build) and generated files are committed or listed in `.gitignore` with a setup step documented.

---

## 6. Query Files & TPC-H Corpus (DC-05, DC-06)

### Directory Structure
```
queries/
  sqlite/           — TPC-H queries against SQLite catalog
    01-select.sql
    02-join.sql
    ...
  postgres/         — TPC-H queries against PostgreSQL catalog
    01-select.sql
    ...
  mysql/            — TPC-H queries against MySQL catalog
    ...
  flightsql/        — TPC-H queries against FlightSQL catalog
    ...
  duckdb/           — TPC-H queries against DuckDB catalog
    ...
  cross-join/       — Cross-driver federation queries
    sqlite-postgres-join.sql
    sqlite-mysql-join.sql
    flightsql-postgres-join.sql
    ...
```

### TPC-H Data Scale
Per D-06: SF1 (~1GB total across all backends). Each backend gets the full TPC-H schema (8 tables: region, nation, part, supplier, partsupp, customer, orders, lineitem) plus seed data. The seed data from the reference project (5 regions, 25 nations, 5 orders, 4 lineitems) is sufficient for correctness verification — not benchmarking.

### Cross-Driver JOIN Corpus
The existing `test_cross_join.py` tests (2 tests: SQLite-PostgreSQL, two-SQLite) serve as the baseline. Additional cross-driver JOIN queries externalized to `queries/cross-join/`:
- `sqlite-postgres-join.sql` — employees (SQLite) JOIN departments (PostgreSQL)
- `flightsql-postgres-join.sql` — TPC-H orders (FlightSQL) JOIN lineitem (PostgreSQL)
- `mysql-postgres-join.sql` — cross-engine federation

---

## 7. Developer Experience Tooling (DC-07, DC-08, DC-09, DC-10)

### run-verify.py (DC-09)
Python CLI using argparse. Per D-07:

```bash
./run-verify.py /path/to/starrocks-fe.deb /path/to/starrocks-be.deb
```

**Flow:**
1. Validate .deb files exist
2. Copy .debs to `docker/starrocks-fe_*.deb` and `docker/starrocks-be_*.deb`
3. `docker compose up --build --detach` (builds images, starts containers)
4. Wait for all services healthy (poll `docker compose ps --format json`)
5. `pytest tests/ -v`
6. Capture exit code
7. Print summary report
8. (Optional) `docker compose down` if `--cleanup` flag

**Options:**
- `--keep` (default): Leave containers running after tests
- `--cleanup`: `docker compose down` after tests
- `--subset <filter>`: Pass through to `pytest -k <filter>`
- `--report <file>`: Output JSON report to file
- `--skip-rebuild`: Skip `--build` flag (reuse existing images)

### Log Capture on Failure (DC-08)
Extended `capture_on_failure` fixture:
1. On test failure, run `docker compose logs --tail=50` (all services)
2. Also capture specific service logs: `docker compose logs sr-main --tail=100`
3. Attach to pytest `user_properties` for JSON report
4. If `--report` flag used on CLI, include logs in report file

### Fast Iteration Path (DC-10)
Documented workflow, not a separate script:
```bash
# Fast iteration after initial setup:
docker compose up -d                # reuse existing containers
pytest tests/ -k flightsql          # run subset
```
No special CLI flag needed — `pytest -k` is the standard mechanism.

### Ship→Verify→Retest Loop (DC-07)
The `run-verify.py` script IS the loop. Each invocation:
1. Copies fresh .debs
2. Rebuilds StarRocks image (Docker layer caching keeps unchanged layers)
3. Re-runs tests
4. Reports results

For iteration without .deb changes: `docker compose up -d && pytest tests/ -v`

### Requirements Mapping
- DC-07 (ship→verify→retest loop): `run-verify.py` script
- DC-08 (log capture on failure): Extended `capture_on_failure` fixture
- DC-09 (CLI runner): `run-verify.py` with argparse
- DC-10 (fast iteration): Documented `pytest -k` + container reuse pattern

---

## 8. Implementation Order

The ROADMAP.md specifies 3 sequential plans:

**Plan 01-01 (Docker Compose Foundation):** `docker-compose.yml`, Dockerfile, entrypoint.sh, backend init SQL, adapted conftest.py, driver path constants. All 35 tests pass against Compose. Retired `lib/docker_backends.py` and `lib/starrocks.py` startup functions. Requirements: DC-01, DC-02, DC-03, DC-04, VAL-01 through VAL-07.

**Plan 01-02 (TPC-H Depth):** TPC-H data generation, pre-baked .db files, `queries/` directory structure, cross-driver JOIN query files, PostgreSQL DECIMAL fix. Requirements: DC-05, DC-06, VAL-06.

**Plan 01-03 (Developer Experience):** `run-verify.py` CLI, extended log capture, pre-generated TLS certs, documented fast iteration path. Requirements: DC-07, DC-08, DC-09, DC-10.

**Why sequential:** Plan 02 depends on Plan 01's working Compose environment (can't load TPC-H data into non-existent containers). Plan 03 wraps Plan 01+02 results (CLI runs the Compose env + tests that don't exist yet).

---

## 9. Risk Register

| Risk | Impact | Mitigation |
|------|--------|-----------|
| ADBC driver .so files not compatible with Ubuntu 24.04 in container | Blocking | Verify driver arch (amd64 linux) matches. Drivers from `dbc install` are statically linked or dynamically linked against standard glibc — should be compatible. |
| StarRocks .deb expects specific filesystem layout | Medium | Reference project already proves this works with Ubuntu 24.04. Config paths are standard (`/etc/starrocks/`). |
| sqlflite image doesn't support init scripts | Low | Use pre-baked .db files mounted as volumes instead of init SQL. |
| Docker Compose healthcheck timing too aggressive | Low | Reference project uses similar timing; adjustable via env vars. |
| TPC-H SF1 data generation time slows build | Medium | Pre-generate once, commit seed SQL. SF1 subset (not full scale) keeps build fast. |
| Cross-driver JOINs fail due to Docker DNS resolution in BE | Medium | Reference project proves Docker DNS (`rtv-sr1`, `rtv-pg1`) works from StarRocks BE. Our service names follow same pattern. |
| Priority_networks patching fails on some Docker network configs | Low | Reference project uses identical patching. `/24` subnet from container IP is standard Docker bridge behavior. |
| Host running tests can't reach StarRocks MySQL port | Low | Port 9030 published in docker-compose.yml, mapped to host. |
| FlightSQL TLS cert extraction timing | Low | Pre-generated certs eliminate runtime extraction race condition. |

---

## 10. Open Questions (the agent's Discretion — resolved during planning)

These were listed as the agent's discretion in CONTEXT.md. Research has resolved most:

1. **Exact Dockerfile structure:** Single-stage Ubuntu 24.04, proven by reference project ✅
2. **Entrypoint script details:** Modeled after reference entrypoint with added driver path config ✅
3. **Conftest fixture refactoring specifics:** Detailed above with exact constant values and fixture signatures ✅
4. **TPC-H data generation mechanism:** Pre-baked .db files via Python script + SQL init files for server-based backends ✅
5. **TLS certificate handling:** Pre-generated self-signed certs mounted as volumes ✅
6. **run-verify.py report format:** Both plain-text terminal output + optional JSON file ✅
7. **FlightSQL TLS service design:** Separate Compose service (`sr-flightsql-tls`) ✅

---

## Standards & Conventions

### Docker Compose Patterns
- Service names: `sr-{name}` prefix (consistent with reference project's `rtv-` prefix)
- Container names match service names for easy `docker compose logs sr-main`
- All services on single bridge network `sr-net`
- Healthchecks use appropriate protocol-specific checks (not just TCP)
- start_period gives slow-starting services (SR, MySQL) time before healthcheck fails count

### Python Patterns
- Session-scoped fixtures for connections (SR, catalogs)
- Module-scoped fixtures for data seeding → replaced by pre-baked data
- Driver paths as module-level constants (not runtime TOML resolution)
- `try: ... finally: drop_catalog()` pattern preserved
- Pytest markers preserved for subset test execution

### Shell Scripting
- Entrypoint uses `#!/bin/bash` with `set -e`
- Port polling with `nc -z` (available via netcat-openbsd)
- MySQL commands use `-h127.0.0.1` (container-local, not Docker DNS)

### Security
- All credentials in environment variables or init scripts (not in Dockerfile)
- No production secrets — test credentials only (`testuser/testpass`, `root/`)
- TLS certs are self-signed for testing, not CA-signed
- Docker bridge network isolates services from host network except published port 9030

---

## Validation Architecture

### What Gets Tested
1. **Infrastructure:** `docker compose up --build` starts all services, healthchecks pass
2. **Driver loading:** All 5 ADBC drivers load in StarRocks (CREATE EXTERNAL CATALOG succeeds)
3. **Data access:** Queries return expected results from each backend
4. **Cross-driver federation:** JOINs across different ADBC backends produce correct results
5. **Error paths:** Bad URIs, wrong credentials, unknown properties produce clear errors
6. **TLS:** Encrypted connections work with self-signed certs
7. **CLI tooling:** `run-verify.py` orchestrates full cycle, captures logs on failure

### How It Gets Tested
- Existing 35-test suite adapted to Compose environment (VAL-01 through VAL-07)
- `docker compose ps` health verification in CLI
- Manual smoke test: `docker compose up --build && pytest tests/ -v`

---

*Research completed: 2026-04-27*
*Source code analyzed: conftest.py, lib/*, tests/*, reference project docker/*
*Pattern source: `/home/mete/coding/remote_table_verification/docker/`*
