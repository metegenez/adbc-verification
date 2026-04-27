# Pitfalls Research

**Domain:** Docker Compose-based database verification suites (StarRocks ADBC + multi-backend)
**Researched:** 2026-04-27
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: driver_url Path Mismatch — Host Path vs Container Path

**What goes wrong:**
`CREATE EXTERNAL CATALOG` fails with "file not found" because the `driver_url` property points to a host filesystem path (e.g., `/home/user/.config/adbc/drivers/libadbc_driver_flightsql.so`) that does not exist inside the StarRocks container.

**Why it happens:**
The existing `lib/driver_registry.py` reads `.so` paths from `~/.config/adbc/drivers/*.toml` on the **host**. When tests run against a locally-started StarRocks, these host paths work because StarRocks processes share the host filesystem. In Docker Compose, the BE process runs inside a container with its own filesystem. ADBC drivers are loaded at runtime by the BE process at the path specified in `driver_url` — this path must be resolvable from within the container.

**How to avoid:**
- Copy ADBC driver `.so` files into the Docker image (at a fixed path like `/opt/starrocks/drivers/`) during `docker build`.
- Use environment variables (e.g., `ADBC_FLIGHTSQL_DRIVER`) in conftest.py that default to container-internal paths: `/opt/starrocks/drivers/libadbc_driver_flightsql.so`
- Never call `get_driver_path()` from the host when using Docker Compose — that registry resolves host paths.
- In conftest.py, detect whether running against Docker Compose (e.g., check for `DOCKER_COMPOSE=1` env var) and switch path sources.

**Warning signs:**
- "Failed to load ADBC driver: /home/user/.config/..." in StarRocks BE logs
- `CREATE EXTERNAL CATALOG` succeeds but catalog shows 0 databases (driver loaded but couldn't connect)
- Test failures only in Docker Compose mode, not in local StarRocks mode

**Phase to address:**
DC-02 (StarRocks container Dockerfile: COPY drivers into image) + DC-04 (pytest conftest adaptation)

---

### Pitfall 2: DNS Resolution — 127.0.0.1 vs Docker Compose Service Names

**What goes wrong:**
Connection URIs like `grpc://127.0.0.1:9408` or `postgresql://127.0.0.1:5432/tpch` work from the host but fail from inside the StarRocks container because 127.0.0.1 inside a container resolves to itself, not to backend services on the Docker network.

**Why it happens:**
In the existing test suite (`docker_backends.py`), Docker containers are started with `--publish` flags mapping to host ports, and tests connect from the host using `127.0.0.1:<host_port>`. In Docker Compose, the StarRocks container initiates outbound connections to backend services over the internal Docker network — it must use service names (DNS) or the Docker network bridge gateway. Developers copy existing test patterns and use 127.0.0.1 without realizing the runtime context has changed.

**How to avoid:**
- In the Docker Compose conftest.py, all URIs must use Docker Compose service names: `grpc://rtv-sr1:9408`, `postgresql://rtv-pg1:5432/tpch`
- Load backend hostnames from environment variables with Docker Compose service name defaults (as the reference project does with `SR_NODE1_HOST`, `PG1_HOST`, etc.)
- Do NOT use `127.0.0.1` or `localhost` in any connection URI intended for cross-container communication.
- The host-to-StarRocks connection (pytest → StarRocks MySQL port) is the only connection that uses 127.0.0.1 (via a published port).

**Warning signs:**
- "Connection refused" or "No route to host" in BE logs when trying to connect to backend
- CREATE EXTERNAL CATALOG succeeds but SHOW DATABASES FROM catalog returns empty or errors
- Tests pass when running StarRocks locally but fail in Docker Compose

**Phase to address:**
DC-04 (pytest conftest adaptation: URI configuration)

---

### Pitfall 3: priority_networks Configuration Race Condition

**What goes wrong:**
StarRocks FE/BE fails to bind to the correct network interface in a Docker container. The FE starts but is unreachable, or the BE never registers with the FE. `<h3>restarting: FE fails</h3>loop`.

**Why it happens:**
StarRocks uses `priority_networks` in `fe.conf`/`be.conf` to determine which IP address to bind to. In Docker, the container IP is assigned dynamically at runtime by the Docker bridge network — it cannot be hardcoded in the Dockerfile. If `priority_networks` is not set, StarRocks may bind to `127.0.0.1`, making it unreachable from outside the container. If set too narrowly (e.g., `/32` subnet), StarRocks may bind to localhost. Additionally, stale PID files from previous container runs (if the container is recreated but the image has stale state) prevent FE/BE startup.

**How to avoid:**
- In the entrypoint script, resolve the container IP at runtime: `CONTAINER_IP=$(hostname -i | awk '{print $1}')`
- Patch `priority_networks` with a `/24` subnet (not `/32`): `echo "priority_networks = $CONTAINER_SUBNET" >> /etc/starrocks/fe/fe.conf`
- Clean stale PID/lock files at container start: `rm -f /usr/lib/starrocks/fe/bin/fe.pid /var/lib/starrocks/fe/meta/lock /usr/lib/starrocks/be/bin/be.pid`
- The reference project (`remote_table_verification/docker/entrypoint.sh`) has the proven pattern for all of this.

**Warning signs:**
- FE port 9030 never opens, or opens but is only reachable from localhost
- BE registers but shows as "false" in SHOW BACKENDS
- `hostname -i` in the entrypoint returns multiple IPs — Docker sometimes assigns both IPv4 and IPv6. Pipe through `awk '{print $1}'` to grab the first one.
- BE log shows "failed to bind to port 9060" or "failed to register with FE"

**Phase to address:**
DC-01 (Docker Compose + Dockerfile + entrypoint.sh)

---

### Pitfall 4: depends_on Without Healthcheck = Race Condition Between Service Readiness

**What goes wrong:**
Tests fail intermittently with connection errors because `docker compose up` returns before StarRocks is actually ready to accept queries. PostgreSQL/MySQL backend containers are started but not yet initialized, causing `CREATE EXTERNAL CATALOG` to fail or return empty results.

**Why it happens:**
Docker Compose's `depends_on` only guarantees container startup order — it waits for the container process to start, NOT for the service inside it to be ready. StarRocks FE takes 30-60 seconds to initialize (metadata loading, port binding). PostgreSQL takes 2-5 seconds after the port opens for the data directory to be ready. MySQL needs `mysqladmin ping` (not just TCP port open) to confirm readiness. Without `condition: service_healthy`, the StarRocks container starts before backend databases are initialized.

**How to avoid:**
- Configure healthchecks on ALL services in docker-compose.yml: PostgreSQL (`pg_isready`), MySQL (`mysqladmin ping`), StarRocks (`mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"`), FlightSQL backends (`nc -z 127.0.0.1 9030`)
- Use `depends_on: condition: service_healthy` (not bare `depends_on`) on the StarRocks main service
- Set generous `start_period` values (30-60s) and high `retries` (30+) for StarRocks services
- In the test runner script (DC-07/DC-09), wait for the StarRocks MySQL port to be open on the published host port before running pytest. A simple `nc -z 127.0.0.1 <HOST_PORT>` loop is sufficient.

**Warning signs:**
- "connection refused" or "Connection reset" errors that disappear on retry
- Tests pass when run individually but fail when run as a full suite (cold start)
- `docker compose up` returns, but `mysql -h127.0.0.1 -P<HOST_PORT>` fails for the first 30+ seconds

**Phase to address:**
DC-01 (docker-compose.yml healthcheck configuration) + DC-07 (runner script wait loop)

---

### Pitfall 5: TPC-H DECIMAL Column Incompatibility Across ADBC Drivers

**What goes wrong:**
Queries against TPC-H tables exposed via PostgreSQL ADBC catalogs fail with "unsupported Arrow type" or return NULL for all DECIMAL columns. This affects `l_quantity`, `l_extendedprice`, `l_discount`, `l_tax`, `o_totalprice` — which are the core measurement columns in TPC-H.

**Why it happens:**
The PostgreSQL ADBC driver returns DECIMAL columns as Arrow opaque extension types, NOT as Arrow decimal128 types. StarRocks' Arrow-to-StarRocks-type conversion does not handle opaque extension types. This is a known limitation in the ADBC PostgreSQL driver — not a StarRocks bug per se, but a mismatch in Arrow type representation strategies between the two projects. TPC-H is DECIMAL-heavy (5 of 16 columns in `lineitem` are DECIMAL), making this a critical blocker for cross-driver TPC-H queries.

**How to avoid:**
- For PostgreSQL-exposed TPC-H tables, pre-create VIEWs that CAST DECIMAL columns to DOUBLE: `CREATE VIEW lineitem_double AS SELECT l_orderkey, l_partkey, ..., CAST(l_quantity AS DOUBLE PRECISION) AS l_quantity, ...`
- OR pre-create the TPC-H tables with DOUBLE PRECISION instead of DECIMAL for PostgreSQL backend
- OR document DECIMAL columns as a known limitation and skip those columns in cross-driver test assertions
- For FlightSQL backends (StarRocks-to-StarRocks), DECIMAL works fine — this is PostgreSQL-specific

**Warning signs:**
- `SELECT * FROM catalog.db.lineitem` returns NULL for price/quantity columns
- BE log contains "Unsupported Arrow type: extension" or "Failed to convert DECIMAL"
- Test assertions on numeric fields fail with None or zero values

**Phase to address:**
DC-03 (TPC-H data pre-loading: PostgreSQL type mapping) + DC-05 (TPC-H query corpus)

---

### Pitfall 6: Init SQL Running Before BE Stabilization in StarRocks

**What goes wrong:**
SQL initialization scripts in `/docker-entrypoint-initdb.d/` execute against the StarRocks FE as soon as the MySQL port is open, but `CREATE TABLE` and `INSERT` statements require at least one alive BE. If the BE hasn't registered yet (or if `ALTER SYSTEM ADD BACKEND` hasn't run), DDL succeeds (metadata-only) but INSERT fails with "no backend available."

**Why it happens:**
StarRocks has a two-phase startup: FE starts first (port 9030 opens quickly), then BE starts and registers. The init SQL scripts run after the FE port is open but before the BE is registered/alive. In the reference project's entrypoint, there's a gap: the BE is started and `ALTER SYSTEM ADD BACKEND` is issued, but the init scripts can run before the BE shows as "true" in `SHOW BACKENDS`. The reference project mitigates this with a 5-second sleep before init scripts and a 30-second polling loop for BE liveness.

**How to avoid:**
- In the entrypoint script: wait for BE to be alive in `SHOW BACKENDS` (not just for the BE port to open) BEFORE running init SQL scripts
- Use a polling loop: `mysql -uroot ... -e "SHOW PROC '/backends'" | grep -c true`
- After BE is alive, add a 5-second grace period for BE to fully stabilize before running DDL
- Wrap init SQL execution in a retry loop: if INSERT fails, sleep 5s and retry (up to 3 attempts)
- For data sources that also have init SQL (PostgreSQL `init-pg.sql`), the `docker-entrypoint-initdb.d` mechanism works reliably because PostgreSQL initializes synchronously before accepting connections.

**Warning signs:**
- Init SQL logs show "INSERT failed: no backend available" or "no alive backend"
- Tables exist (from DDL) but are empty (INSERT failed silently)
- `SHOW PROC '/backends'` shows backend count = 0 when init scripts run

**Phase to address:**
DC-01 (entrypoint.sh: BE readiness check before init SQL)

---

### Pitfall 7: Volume Mounts Overwriting Container-Generated Files

**What goes wrong:**
When mounting host directories into container paths that contain auto-generated files, the mount replaces the entire directory, breaking file generation. Specifically, sqlflite generates TLS certificates at `/opt/sqlflite/tls/root-ca.pem` at startup. Mounting a host directory at `/opt/sqlflite/tls/` prevents certificate generation.

**Why it happens:**
Docker bind mounts operate at the directory level — they replace the entire target directory with the host directory contents. This is documented in Docker's bind mount behavior: "the pre-existing files become obscured by the mount." When containers generate files at startup into a mounted directory, the generated files either don't appear (written to the in-container overlay, not the host mount) or fail entirely.

**How to avoid:**
- Use `docker cp` to extract generated files AFTER the container starts, rather than volume-mounting the target directory. The reference project does this for sqlflite TLS certs (`tls.py` uses `docker cp`).
- If volume-mounting init SQL scripts, mount to a dedicated subdirectory (`/docker-entrypoint-initdb.d/`) — never mount the parent directory where the container writes runtime state.
- For postgres data persistence, use named volumes (Docker-managed) rather than bind mounts to avoid host filesystem permission issues.
- **Exception:** Init SQL scripts (`/docker-entrypoint-initdb.d/`) ARE safe to bind mount because the container reads from them but doesn't write to them.

**Warning signs:**
- Container start fails because it can't write to a mounted directory
- Generated files are missing when inspected via `docker exec`
- TLS test failures with "certificate not found" after successful-looking container start

**Phase to address:**
DC-01 (docker-compose.yml volume configuration) + DC-03 (backend service configuration)

---

### Pitfall 8: Stale Container State Between Test Runs

**What goes wrong:**
Docker Compose `down` followed by `up` retains database volumes, leading to stale schema/data from a previous test run. Re-running tests without a clean slate causes false positives (old data passes tests that should fail) or false negatives (schema drift from updated init SQL not applied).

**Why it happens:**
`docker compose down` stops and removes containers but preserves named volumes by default. `docker compose down -v` removes volumes but also removes ALL volumes, including those shared between services. Docker Compose-managed Postgres containers only run `/docker-entrypoint-initdb.d/` scripts when the data directory is empty (first start). Re-using volumes means init scripts never re-run.

**How to avoid:**
- In the test runner script (DC-07/DC-09): always run `docker compose down -v` before `docker compose up --build` to ensure a clean state. If you need to preserve some volumes, name them specifically and selectively remove them.
- For the fast iteration path (DC-10): skip `-v` on `down` only when you're certain the data hasn't changed. Provide a `--clean` flag on the CLI runner for explicit full cleanup.
- In CI/CD (future): always use `docker compose down -v` since runners are ephemeral.
- Consider using Docker Compose `profiles` or separate `docker-compose.test.yml` overrides to isolate test-specific volumes.

**Warning signs:**
- Tests pass after running `docker compose up` but fail after `docker compose down -v && docker compose up --build`
- Schema changes to init SQL don't take effect (old columns still exist)
- Data counts don't match expectations despite correct init SQL

**Phase to address:**
DC-07 (ship→verify→retest loop script) + DC-09 (CLI runner)

---

### Pitfall 9: DEB Package Installation Artifacts in Docker Build Cache

**What goes wrong:**
The Dockerfile `dpkg -i *.deb` step succeeds on first build but fails on subsequent builds with "package is already installed" or "conflicting files" errors. Alternatively, the Docker build cache serves a layer with stale DEB contents, and code changes in the rebuilt DEB aren't picked up.

**Why it happens:**
`dpkg -i` tracks installed packages in `/var/lib/dpkg/`. When Docker caches the layer containing the `dpkg -i` step, it reuses it even when the DEB file on disk has changed (because the COPY of the DEB is a separate layer with its own cache key). The Docker build cache detects changes to the DEB file (via checksum) and invalidates the COPY layer, but the `dpkg -i` and cleanup layer may still be cached. Additionally, DEB packages may contain systemd service files, init scripts, or default configs that conflict with containerized operation.

**How to avoid:**
- Chain the COPY and dpkg operations into a single RUN command: `RUN dpkg -i /tmp/starrocks-fe_*.deb /tmp/starrocks-be_*.deb && rm /tmp/*.deb`. This ensures the dpkg step always runs when the COPY layer changes.
- Set `DEBIAN_FRONTEND=noninteractive` in the Dockerfile to prevent dpkg from trying to prompt during installation.
- Clean package cache after installation: `apt-get clean && rm -rf /var/lib/apt/lists/*`
- The reference project's Dockerfile already uses this pattern correctly.
- For the fast iteration path (DC-10): use `docker compose up --build` (forces rebuild) rather than relying solely on cache. Use `--no-cache` when in doubt.

**Warning signs:**
- `docker build` succeeds but the running container has old StarRocks version
- "package architecture (amd64) does not match system (i386)" when building on ARM/M1
- dpkg error about "trying to overwrite '/etc/...' which is also in package ..." from conflicting config files

**Phase to address:**
DC-02 (Dockerfile optimization: cached layer semantics)

---

### Pitfall 10: FlightSQL Port Confusion — FE 9408 vs BE 9419

**What goes wrong:**
FlightSQL catalogs are created pointing to port 9419 (BE Arrow Flight port) instead of 9408 (FE Arrow Flight port), resulting in connection failures or "no such service" errors.

**Why it happens:**
StarRocks has TWO Arrow Flight ports: port 9408 on the FE (for FlightSQL query processing) and port 9419 on the BE (for internal data transfer). The ADBC FlightSQL driver must connect to the FE's port 9408. Developers see both ports in documentation and may use the wrong one, especially since port 9419 is the Arrow Flight port for BE data streaming.

**How to avoid:**
- Document prominently in the Docker Compose conftest.py and in docker-compose.yml comments: "FlightSQL port is 9408 (FE), NOT 9419 (BE)"
- Use named constants or environment variables with clear names: `FLIGHTSQL_FE_PORT=9408` (not `ARROW_FLIGHT_PORT=9419`)
- In docker-compose.yml, publish BOTH ports but label them clearly in comments to avoid confusion
- Add a smoke test in the test suite that explicitly verifies FlightSQL connectivity on 9408

**Warning signs:**
- FlightSQL catalog creation succeeds but SHOW DATABASES returns nothing or errors
- "gRPC status: Unavailable" or "Failed to connect to Flight server on port 9419"
- The BE logs show Arrow Flight connections arriving on 9419 — that's for BE data transfer, not FlightSQL queries

**Phase to address:**
DC-01 (docker-compose.yml: correct port mappings with comments) + DC-04 (conftest.py: documented FlightSQL port constant)

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoding host ports in conftest.py (e.g., `49030` directly) | No env var setup needed | Can't run multiple instances; port conflicts with other projects | Only for single-developer local dev; NEVER in a shared Docker Compose setup |
| Copy-pasting the existing `docker_backends.py` `127.0.0.1` URIs into Docker Compose conftest | Fast to write | Every test fails mysteriously because 127.0.0.1 inside container means "self" | Never — use Docker Compose service names from the start |
| Using bare `depends_on` without `condition: service_healthy` | Yaml is simpler | Intermittent failures that waste hours debugging; flaky CI | Only for stateless services that are instantly ready (never for databases) |
| Not cleaning `.pid`/`.lock` files in the entrypoint | Simpler entrypoint script | Container restart fails after crash/kill; needs manual intervention | Only if the container is ALWAYS destroyed and recreated (Docker Compose down -v every time) |
| Skipping init SQL retry logic (assuming BE is always ready) | Entrypoint starts faster | Silent data loss: tables created but empty; tests pass by accident on cached data | Never — BE startup is inherently async in StarRocks |
| Using the same container names as the existing test suite (`adbc_test_*`) | No naming work | Docker Compose and manual containers collide; hard to debug which container is which | Only for throwaway experiments — use project-specific prefixes |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PostgreSQL ADBC | Expecting `DECIMAL` columns to return as Arrow decimal128 | Cast to DOUBLE or TEXT in VIEWs; document DECIMAL as known limitation |
| FlightSQL | Connecting to BE port 9419 instead of FE port 9408 | Always use FE port 9408; the FlightSQL service lives on the FE |
| MySQL (StarRocks) | Connecting before BE registers | Wait for `SHOW BACKENDS` to show "true" for at least one backend |
| Docker Compose DNS | Using `localhost` or `127.0.0.1` for cross-container connections | Use Docker Compose service names: `grpc://service-name:port` |
| DEB packages | Expecting DEBs to work without JDK | StarRocks FE requires `openjdk-17-jre-headless` — install in Dockerfile |
| sqlflite TLS | Volume-mounting `/opt/sqlflite/tls/` expecting certs to appear | Use `docker cp` to extract certs AFTER container generates them |
| Multi-service Docker Compose | Publishing ALL backend ports to the host | Most backends only need Docker network connectivity; only publish the StarRocks MySQL port |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| TPC-H data seeded via INSERT statements in init SQL | Container startup takes minutes with scale-factor 1+ TPC-H data | Use PostgreSQL `COPY` or generate data via a separate tool; pre-build data images | >100 rows per table |
| No Docker layer caching for DEB installation | Full `docker build` runs every time even when DEB hasn't changed | COPY the DEB first, then RUN dpkg (separate layers); Docker caches dpkg layer when DEB checksum unchanged | Every rebuild |
| All backend containers start simultaneously with resource limits | Docker Desktop / CI runner OOM kills containers | Use `depends_on` to stagger startup; add `deploy.resources.limits` | >3 database containers on 4GB RAM |
| Mounting TPC-H SQL files as volumes at runtime | Slow container startup as SQL is parsed every time | Pre-load data into Docker images (multi-stage build); use SQL files only for schema changes | Scale factor >0.01 |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Hardcoding ADBC driver passwords in conftest.py | Credentials in git history; leaking to test reports | Use environment variables with defaults (like the reference project: `os.environ.get("...", "default")`) |
| Publishing BE ports (9419, 9060) to the host | Exposing internal StarRocks data transfer ports to host network | Only publish FE MySQL port (9030) and optionally FE HTTP port (8030); keep BE ports internal to Docker network |
| TLS certs extracted to `/tmp` without cleanup | Cert files persist on host filesystem between test runs | Use `tempfile.mkdtemp()` and clean up in fixture teardown (already done in `lib/tls.py`) |
| PostgreSQL with `trust` auth in Docker Compose | Backend accepts any connection without password | Always set POSTGRES_PASSWORD and use SCRAM-SHA-256 (default in postgres:16); use `pg_hba.conf` overrides for stricter network rules if needed |

## UX Pitfalls

Common user experience mistakes for the CLI runner (DC-09).

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No progress output during `docker compose up --build` | User stares at blank terminal for 2+ minutes wondering if it's stuck | Tail relevant container logs or show spinner with elapsed time |
| Silent failures when DEB is malformed | User thinks tests passed because containers started but data is missing | Validate DEB file size/checksum before building; healthcheck must fail if BE doesn't register |
| `docker compose down` doesn't clean up by default | Orphan containers and volumes accumulate, consuming disk space | CLI runner should offer `--down` and `--clean` flags; default behavior should be documented |
| Test output mixes Docker Compose logs with pytest output | Hard to distinguish infrastructure failures from test failures | Capture Docker logs to separate files; only surface them in test output on failure (DC-08) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Dockerfile builds and container starts:** Does `SHOW BACKENDS` show at least one "true"? Container starting doesn't mean StarRocks is functional.
- [ ] **docker-compose.yml has depends_on:** Are there `condition: service_healthy` entries? Bare `depends_on` doesn't wait for readiness.
- [ ] **Init SQL runs and tables exist:** Are they populated with data? Tables can exist (DDL) but be empty if INSERT failed due to no alive BE.
- [ ] **CREATE EXTERNAL CATALOG succeeds:** Can you actually query data from it? Catalogs can be created even when the backend is unreachable — they'll just return empty results.
- [ ] **Cross-container queries work:** Are you querying via Docker Compose service names or hardcoded 127.0.0.1? The latter only works by accident if services are on the same host.
- [ ] **driver_url points to container path:** Is it `/opt/starrocks/drivers/libadbc_driver_*.so` or a host path like `/home/user/.config/adbc/drivers/...`? The host path only works in local mode.
- [ ] **TPC-H DECIMAL columns work:** Have you tested `SELECT * FROM postgres_catalog.public.lineitem`? Does it return actual numbers or NULL/errors for price/quantity columns?

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| driver_url path mismatch | LOW | Set correct `ADBC_*_DRIVER` env var; rebuild; test |
| 127.0.0.1 vs service names | LOW | Update conftest.py connection URIs; rebuild; test |
| priority_networks not set | MEDIUM | Fix entrypoint.sh to patch at runtime; rebuild image; restart |
| Missing healthcheck conditions | LOW | Add `condition: service_healthy` to docker-compose.yml; `docker compose up -d` |
| DECIMAL column incompatibility | MEDIUM | Create VIEWs with CAST to DOUBLE in init-pg.sql; or alter table schema |
| Init SQL before BE ready | MEDIUM | Add BE liveness check in entrypoint.sh; rebuild image; restart |
| Volume mount overwrites certs | LOW | Switch from volume mount to `docker cp` in test fixtures |
| Stale container state | LOW | Run `docker compose down -v` before `docker compose up --build` |
| FlightSQL wrong port | LOW | Update port from 9419 to 9408 in conftest.py |
| DEB cache inconsistency | MEDIUM | `docker compose build --no-cache`; fix Dockerfile layer ordering |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| driver_url path mismatch | DC-02, DC-04 | `SHOW DATABASES FROM <catalog>` must return expected databases |
| 127.0.0.1 vs service names | DC-04 | Cross-container ping from StarRocks container: `docker exec sr-main nc -z rtv-pg1 5432` |
| priority_networks race | DC-01 | `SHOW BACKENDS` returns "true" after container start; BE log shows correct IP binding |
| depends_on without healthcheck | DC-01 | `docker compose up` returns only after all healthchecks pass |
| DECIMAL column incompatibility | DC-03, DC-05 | `SELECT l_extendedprice FROM postgres_catalog.public.lineitem LIMIT 1` returns a number, not NULL |
| Init SQL before BE ready | DC-01 | All TPC-H tables are populated (row counts >0) after container start |
| Volume mount overwrites | DC-01, DC-03 | TLS cert files exist and are readable after container start |
| Stale container state | DC-07, DC-09 | Two consecutive `up → test → down` cycles produce identical results |
| FlightSQL port confusion | DC-01, DC-04 | FlightSQL catalog queries return results from port 9408 |
| DEB cache inconsistency | DC-02 | `docker compose up --build` after DEB rebuild shows updated version in `SELECT @@version_comment` |

## Sources

- `remote_table_verification/CLAUDE.md` — reference project's documented pitfalls (PostgreSQL DECIMAL issue, FlightSQL port 9408 vs 9419, driver_url container path)
- `remote_table_verification/docker/entrypoint.sh` — proven priority_networks patching pattern, BE readiness wait loop, init SQL delay
- `remote_table_verification/docker/Dockerfile` — DEB installation pattern with `dpkg -i && rm`
- `adbc_verification/lib/docker_backends.py` — existing Docker container lifecycle with `--rm`, `_wait_for_port`, and per-service readiness patterns
- `adbc_verification/lib/tls.py` — `docker cp` pattern for extracting generated files (sqlflite TLS certs)
- Context7: Docker Docs (`/docker/docs`) — `depends_on` startup order documentation, healthcheck `condition: service_healthy`, bind mount overwrite behavior, `/docker-entrypoint-initdb.d/` initialization rules
- Context7: Apache Arrow ADBC (`/apache/arrow-adbc`) — driver shared library path requirements, TOML manifest format, FlightSQL connection options
- Context7: StarRocks Docs (`/websites/starrocks_io`) — `priority_networks` configuration pitfalls (avoid `/32` subnet), `CREATE EXTERNAL CATALOG` API
- StarRocks source: Arrow Flight implementation — dual port architecture (FE:9408 for FlightSQL query service, BE:9419 for data transfer)
- Community patterns: Docker Compose testing for databases — `docker compose down -v` best practice for reproducible test environments

---

*Pitfalls research for: Docker Compose-based StarRocks ADBC verification suites*
*Researched: 2026-04-27*
