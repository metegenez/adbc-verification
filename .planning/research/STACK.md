# Stack Research

**Domain:** Docker Compose-based database connector verification suites
**Researched:** 2026-04-27
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker Compose v2 | latest (via `docker compose`) | Multi-container orchestration | Industry standard CLI for defining and running multi-container Docker apps. The v2 plugin (written in Go) replaced the legacy Python `docker-compose` v1. Provides `depends_on` with `condition: service_healthy`, internal DNS-based service discovery, and `--wait` for CI integration. |
| Docker Engine | 24+ | Container runtime | Required by Docker Compose v2. Version 24+ ensures support for all Compose Specification features including `start_period` in healthchecks and the long-form `depends_on` syntax. |
| Ubuntu (base image) | 24.04 (Noble Numbat) | Base image for custom StarRocks container | LTS release matching the StarRocks DEB build host GLIBC 2.38 requirement. Ships Java 17 LTS packages needed by StarRocks FE. 22.04 is too old for newer DEB builds. |
| PostgreSQL | 16 | Backend data source (docker image) | Latest stable major version at the time of the reference project. PostgreSQL 16 has proven initdb performance, `pg_isready` healthcheck tool, and `/docker-entrypoint-initdb.d/` auto-execution for seed data. Version 17 exists but 16 has more community testing for ADBC drivers. |
| MySQL | 8.0 | Backend data source (docker image) | Long-term stable release with proven Docker support, `mysqladmin ping` healthcheck capability, and `/docker-entrypoint-initdb.d/` auto-execution. MySQL 8.4 (LTS) exists but the ADBC MySQL driver is primarily tested against 8.0. |
| SQLite (via FlightSQL) | `voltrondata/sqlflite:latest` | Backend data source (docker image) | Standard FlightSQL implementation wrapping SQLite. Provides Arrow Flight gRPC interface on port 31337. Volta's image is the reference FlightSQL server for ADBC testing. |
| Python | 3.11+ | Test runtime | Mature release with `tomllib` standard library (used for ADBC driver manifest parsing). 3.11 is the minimum specified in `pyproject.toml`. 3.12/3.13 work but bring no essential features for this domain. |
| OpenJDK JRE | 17 (headless) | StarRocks FE runtime | Required by StarRocks FE. Java 17 is the LTS version packaged as `openjdk-17-jre-headless` in Ubuntu 24.04. Java 21 works but is not in Ubuntu 24.04 default repos without additional PPAs. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.x | Test framework | All tests. Version 8 is the current major release with improved fixture scoping, better error reporting, and `--json-report` compatibility. Already in `pyproject.toml`. |
| pymysql | 1.1+ | MySQL wire protocol client for StarRocks | Every test fixture that connects to StarRocks FE. Pure-Python MySQL driver that handles the StarRocks MySQL-compatible protocol on port 9030. Already in `pyproject.toml`. |
| pytest-json-report | 1.5+ | Structured test output | CI and reporting. Produces machine-readable JSON test reports consumed by the ship→verify→retest loop. Already in `pyproject.toml`. |
| tomllib | stdlib (3.11+) | ADBC driver manifest parsing | `lib/driver_registry.py` reads `~/.config/adbc/drivers/*.toml` to resolve driver `.so` paths. No external dependency needed — `tomllib` is in the Python 3.11 standard library. |
| StarRocks DEB packages | `starrocks-fe_*.deb`, `starrocks-be_*.deb` | Database engine | Copied into the Docker build context (`docker/` directory). Installed via `dpkg -i` in the Dockerfile. The `ship-starrocks` skill handles the build→package→copy pipeline. |
| ADBC driver `.so` files | (host-provided) | Database connector drivers | Copied from host `~/.config/adbc/drivers/` or the `docker/drivers/` directory into the container at `/opt/starrocks/drivers/`. Currently requires: `libadbc_driver_sqlite.so`, `libadbc_driver_flightsql.so`, `libadbc_driver_postgresql.so`, `libadbc_driver_duckdb.so`, `libadbc_driver_mysql.so`. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `dbc` (ADBC driver manager) | Install/manage ADBC drivers | `~/.local/bin/dbc install <driver>` installs `.so` files and writes TOML manifests to `~/.config/adbc/drivers/`. Used to source driver files for the Docker image. |
| mysql-client | Healthcheck and debugging | `mysql` CLI binary installed inside the StarRocks container. Used for healthcheck (`mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"`) and entrypoint BE registration. |
| netcat-openbsd | Port readiness checks | Used in container entrypoint scripts and healthchecks (`nc -z 127.0.0.1 9030`) to verify FE/BE ports are listening before proceeding. |
| `docker compose` CLI | Container lifecycle | `docker compose up -d --build` to start; `docker compose down` to stop; `docker compose logs` for failure capture. Host-level tool, not containerized. |
| `ship-starrocks` skill | Build→DEB→copy pipeline | GSD skill that builds StarRocks from source, packages as `.deb`, and copies to the verification suite's `docker/` directory. Automates the inner dev loop. |

## Installation

```bash
# Python environment (already set up)
python3.11 -m venv .venv
.venv/bin/pip install -e .

# ADBC drivers (install on host, copy into Docker image)
~/.local/bin/dbc install sqlite flightsql postgresql duckdb mysql

# Verify driver manifests exist
ls ~/.config/adbc/drivers/*.toml

# Copy drivers into Docker build context for container embedding
mkdir -p docker/drivers/
for driver in sqlite flightsql postgresql duckdb mysql; do
    so_path=$(python3 -c "
import tomllib, pathlib
m = tomllib.loads(pathlib.Path.home() / '.config/adbc/drivers/${driver}.toml').read_text())
print(m['Driver']['shared']['linux_amd64'])
")
    cp "$so_path" docker/drivers/
done
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Docker Compose v2 | Individual `docker run` commands | When you need exactly one container. Not applicable here — the suite manages 5+ containers (StarRocks + 4+ backends) requiring a shared network and startup ordering. |
| Host runs pytest (no pytest-docker plugin) | `pytest-docker` or `pytest-docker-tools` plugins | When tests need to programmatically control container lifecycle at the test level (not session level). Adds complexity; the Compose + `depends_on: service_healthy` pattern handles startup correctly. |
| `compose.yaml` (no `version` key) | `docker-compose.yml` with `version: "3.8"` | Legacy projects. The `version` top-level key was deprecated in the Compose Specification. Modern Compose v2 infers the spec version automatically. |
| Ubuntu 24.04 base | Ubuntu 22.04 or Debian Bookworm | If DEBs are built against GLIBC 2.35 (22.04) instead of 2.38 (24.04). Match the build host distro. |
| PostgreSQL 16 | PostgreSQL 15 or 17 | If the ADBC PostgreSQL driver has known compatibility issues with 16. No such issues are documented. |
| MySQL 8.0 | MySQL 8.4 LTS or MariaDB | If the ADBC MySQL driver is tested primarily against 8.4. Currently 8.0 is the reference. |
| SQL seed data in `.sql` files | TPC-H `dbgen` for runtime data generation | When tests need scalable data volumes (SF-1, SF-10, etc.) for performance benchmarking. This project only needs functional correctness — small deterministic datasets. |
| Bridge network (default) | Host networking (`network_mode: host`) | When containers need to access host services directly. Bridge network provides better isolation and service name DNS resolution. |
| `depends_on` with `condition: service_healthy` | Simple `depends_on: [service]` without condition | When the dependent service doesn't need the dependency to be fully ready. StarRocks FE needs backends fully initialized before CREATE CATALOG works — the basic form only waits for container start, not health. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Legacy `docker-compose` (v1, Python) | Deprecated by Docker. Slower, lacks `--wait`, `condition: service_healthy`, and other Compose Specification features. No longer maintained. | `docker compose` (v2, Go plugin) |
| `version` top-level key in compose file | Deprecated in Compose Specification. Causes warnings in Docker Compose v2.24+. | Omit the `version` key entirely — Compose v2 auto-detects the spec |
| `links` directive in compose files | Legacy Docker feature for service connectivity. Deprecated in favor of Docker network DNS. | `depends_on` (no `links`) — services resolve each other by name on the shared network |
| `network_mode: host` | Breaks container isolation, makes port conflicts likely, defeats Compose service name DNS resolution. | Named bridge network (`networks:`) — default driver is bridge |
| `docker-compose.yml` filename | Stale convention from the v1 era. The modern spec default is `compose.yaml`. | `compose.yaml` — both filenames are accepted but `compose.yaml` is the current convention |
| `pytest-docker` or `pytest-docker-tools` plugins | Add indirection between test code and container lifecycle. The Compose + host pattern is simpler, debuggable, and proven in the reference project. | Docker Compose manages containers; pytest connects to the exposed StarRocks MySQL port from the host |
| Java 8 (openjdk-8-jre) | StarRocks FE requires Java 17+. Java 8 is EOL and incompatible. | `openjdk-17-jre-headless` — packaged in Ubuntu 24.04 |
| TPC-H `dbgen` tool | Adds a C build dependency and custom invocation logic. The seed SQL pattern (small deterministic datasets in `.sql` files) is sufficient for functional verification. | Hand-written seed SQL files mounted at `/docker-entrypoint-initdb.d/` |
| Dockerfile `CMD` for database entrypoint | StarRocks needs sequential startup (FE first, then BE, then registration). A single `CMD` can't express multi-step initialization. | `ENTRYPOINT ["/entrypoint.sh"]` — bash script handles FE start → wait → BE start → wait → register → init SQL → tail log |
| `ports:` exposing all backend containers | Unnecessary — only the StarRocks MySQL port needs host access for pytest. Backend containers communicate internally via the Docker network. | Only publish the StarRocks MySQL port (9030); backends use internal network only |

## Stack Patterns by Variant

**If building from a shipped DEB (this project):**
- Use `dpkg -i` in the Dockerfile to install DEBs
- Copy ADBC drivers into `/opt/starrocks/drivers/`
- Entrypoint shell script handles FE/BE startup and BE registration
- Pattern proven in `/home/mete/coding/remote_table_verification/docker/`

**If building StarRocks from source inside the Dockerfile:**
- Use multi-stage build: build stage (with JDK, Maven, build deps) → runtime stage (JRE only)
- Substantially larger image and slower rebuild (full source + build toolchain)
- Not recommended for the fast ship→test cycle — DEB pre-building is faster

**If running pytest inside a container (CI):**
- Add a `pytest` service to `compose.yaml` that depends on StarRocks with `condition: service_healthy`
- Mount test files as volumes, use `docker compose run pytest`
- Adds complexity; the host-running-pytest pattern is simpler for local dev

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pytest 8.x | pytest-json-report 1.5+ | Verified in `pyproject.toml`. No known issues. |
| pymysql 1.1+ | StarRocks MySQL protocol | StarRocks FE speaks MySQL wire protocol; pymysql is the standard pure-Python driver. |
| PostgreSQL 16 image | ADBC PostgreSQL driver | Driver must support PostgreSQL 16 wire protocol. The ADBC PostgreSQL driver is wire-compatible with 14-17. |
| MySQL 8.0 image | ADBC MySQL driver | Driver must support MySQL 8.0 wire protocol. |
| Ubuntu 24.04 base | GLIBC 2.38 | StarRocks DEBs are built on Ubuntu 24.04 with GLIBC 2.38. Mixing with older GLIBC causes `version 'GLIBC_2.38' not found` errors. |
| Java 17 JRE | StarRocks FE 3.x | Required. Java 21 JRE works but requires a PPA on Ubuntu 24.04. |
| Docker Compose v2 | Docker Engine 24+ | Compose v2 plugin ships with Docker Desktop and `docker-ce` packages. Verify with `docker compose version`. |

## Sources

- Context7 `/docker/compose` — `depends_on` with `condition: service_healthy`, `healthcheck` with `start_period`, Compose Specification format, `docker compose up --wait` (HIGH confidence)
- Context7 `/docker/docs` — `depends_on` long syntax, service dependency patterns, `pg_isready` healthcheck (HIGH confidence)
- Context7 `/websites/docker_reference` — Dockerfile `HEALTHCHECK`, `ENTRYPOINT` exec form, `CMD` rules (HIGH confidence)
- Reference project `/home/mete/coding/remote_table_verification/` — Proven pattern: Dockerfile from DEB, `compose.yaml` with named network, `depends_on`, healthchecks, entrypoint.sh, seed SQL files, pytest from host (HIGH confidence)
- Current project `/home/mete/coding/opensource/adbc_verification/` — Existing `conftest.py`, `lib/`, `pyproject.toml`, test suite with 35 tests (HIGH confidence)
- `ship-starrocks` GSD skill — Build→DEB→copy pipeline, port mapping conventions (HIGH confidence)
- Docker Hub API — PostgreSQL 16, MySQL 8.0 are the current stable tags used in verification projects (MEDIUM confidence)

---
*Stack research for: Docker Compose-based ADBC verification suites*
*Researched: 2026-04-27*
