# Project Research Summary

**Project:** StarRocks ADBC Built-In Verification Suite
**Domain:** Docker Compose-based database connector verification (ADBC catalog integration testing)
**Researched:** 2026-04-27
**Confidence:** HIGH

## Executive Summary

This is a Docker Compose-based end-to-end verification suite that proves StarRocks' ADBC catalog layer correctly federates queries across heterogeneous backend databases (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB, SQLite). A self-contained `docker compose up` brings up a StarRocks container (built from a shipped `.deb` package with all ADBC drivers pre-installed) alongside backend database containers, all communicating over a Docker bridge network. pytest runs from the host, connecting only to the published StarRocks MySQL port, executing a corpus of SQL queries — including cross-driver JOINs that prove federation across entirely different database engines — against the ADBC catalog layer.

The recommended approach follows the proven `remote_table_verification` reference architecture: co-locate StarRocks FE+BE in a single container with an entrypoint script that handles sequential startup (FE → BE → registration → healthcheck), use Docker Compose service names for backend discovery (not `localhost` or hardcoded host ports), gate all service dependencies with `condition: service_healthy`, and keep pytest on the host for fast iteration. The existing 35-test suite already validates the core ADBC functionality; the milestone objective is to replace the manual `docker_backends.py` subprocess pattern with a fully self-contained Docker Compose environment that enables a one-command build→ship→verify→retest loop.

The key risks are all Docker/container-nuance pitfalls: driver path mismatches between host and container filesystems (the BE loads `.so` files from paths specified in `driver_url`, which must resolve inside the container), `priority_networks` binding caused by Docker's dynamic IP assignment, `depends_on` without healthcheck causing flaky startup races, and TPC-H DECIMAL column incompatibility in the PostgreSQL ADBC driver (DECIMAL arrives as Arrow opaque extension types, not `decimal128`). Each has a proven mitigation strategy documented in the pitfalls research, reducing these from blocking risks to known-issue-with-fix.

## Key Findings

### Recommended Stack

The stack layers Docker Compose v2 orchestration over a fleet of purpose-built containers. The StarRocks container (Ubuntu 24.04 base + OpenJDK 17 JRE headless) is built from shipped `.deb` packages — not source-compiled inside the Dockerfile — for fast `ship→test` cycles. ADBC driver `.so` files are copied into the image at build time at a fixed container-internal path (`/opt/starrocks/drivers/`), avoiding host-to-container path resolution problems. Backend databases use stock Docker Hub images (PostgreSQL 16, MySQL 8.0, `voltrondata/sqlflite:latest`) with init SQL mounted at `/docker-entrypoint-initdb.d/` for automatic schema+data seeding. File-based backends (DuckDB, SQLite) ship as pre-built `.db` files inside the StarRocks container. pytest 8.x runs from the host machine, connecting via pymysql to the published MySQL port (127.0.0.1:9030).

**Core technologies:**
- **Docker Compose v2 (latest)**: Multi-container orchestration with `depends_on: condition: service_healthy`, healthcheck-gated startup, Docker DNS service discovery. The `version` key is omitted per Compose Specification. Single `docker compose up --build` starts everything.
- **Ubuntu 24.04 + OpenJDK 17 JRE**: StarRocks FE+BE co-located in one container. Ubuntu 24.04 matches the DEB build host GLIBC 2.38. Java 17 is the required StarRocks FE LTS runtime.
- **PostgreSQL 16, MySQL 8.0, sqlflite**: Backend data sources as separate Docker services. Postgres 16 provides `pg_isready` healthcheck; MySQL 8.0 uses `mysqladmin ping`; sqlflite exposes FlightSQL gRPC on port 31337.
- **Python 3.11+ with pytest 8.x + pymysql**: Host-side test runner. `tomllib` in stdlib for driver manifest parsing. No pytest-docker plugins — the host connects to one published port.
- **ADBC driver `.so` files**: Copied into the StarRocks image at build time. Five drivers: flightsql, postgresql, mysql, sqlite, duckdb. Paths inside the container are fixed (`/opt/starrocks/drivers/`).

### Expected Features

The existing 35-test suite is the baseline — it already covers per-driver test modules, catalog lifecycle, data round-trip, error path testing, TLS verification, adbc.* pass-through, negative tests, and the auto-detected driver registry. The milestone adds three layers:

**Must have (table stakes for milestone completion):**
- **Docker Compose self-containment** — `docker compose up` replaces manual StarRocks startup and individual `docker run` calls. A single command brings up the entire environment. The StarRocks container is built from a `.deb`, with ADBC drivers baked in. Backend databases are named Compose services on a Docker bridge network.
- **Backend database provisioning (Compose mode)** — Replace `lib/docker_backends.py` subprocess calls with Docker Compose service definitions, healthchecks, and init SQL volume mounts. Containers auto-stop on session teardown.

**Should have (adds the depth that justifies the Docker Compose investment):**
- **TPC-H query corpus** — Industry-standard benchmark schema and 22 queries pre-loaded into every backend database. Queries live as standalone SQL files in a `queries/` directory — editable, versionable, and runnable independently of container images. Proves the ADBC connector handles complex SQL (aggregations, JOINs, subqueries, window functions).
- **Externalized SQL queries** — Query files live outside Docker Compose. Test runner reads them, substitutes catalog/database names, executes, asserts. No rebuild needed to change a test query.
- **Cross-driver JOIN verification** — The killer feature: a single StarRocks query JOINs two different ADBC backends (e.g., SQLite ↔ PostgreSQL). Already exists (4 tests) but needs adaptation to Docker Compose service names.

**Defer to v2+ (developer experience polish):**
- CLI runner (`run-verify.sh`) — orchestrates the full build→ship→verify→retest cycle
- Ship→verify→retest loop automation
- Fast iteration path (documented patterns for `-k` subset testing)
- Structured failure diagnostics (Compose log capture extended to backend services)

### Architecture Approach

The architecture follows a **host-as-test-runner** pattern: pytest runs on the host machine, connecting to a single published port (StarRocks MySQL on 127.0.0.1:9030). Everything else lives inside a Docker bridge network where containers communicate via Compose service names (DNS). The StarRocks container co-locates FE and BE processes (started sequentially by an entrypoint script), with ADBC drivers baked into the image at `/opt/starrocks/drivers/`. Backend containers (PostgreSQL, MySQL, FlightSQL) provide data sources — the StarRocks BE loads ADBC drivers at catalog creation time and connects to backends using Docker DNS names (e.g., `sr-pg:5432`). File-based backends (DuckDB, SQLite) use `.db` files inside the StarRocks container. Start-up ordering is gated by healthcheck conditions: backends must be healthy before StarRocks starts; the test runner waits for StarRocks to be healthy before running.

**Major components:**
1. **StarRocks container (sr-main)** — FE+BE from `.deb` packages; hosts all ADBC driver `.so` files; entrypoint script handles sequential startup, `priority_networks` runtime patching, BE registration, and init SQL execution. Exposes MySQL port 9030 to host.
2. **Backend containers (sr-pg, sr-mysql, sr-flightsql)** — Stock Docker images with TPC-H schema/data loaded at startup via `/docker-entrypoint-initdb.d/`. Communicate only on the internal Docker network — no host ports published.
3. **pytest test suite (host)** — Connects to StarRocks MySQL port. Issues `CREATE EXTERNAL CATALOG` commands pointing at Docker network backends. Reads SQL queries from `queries/` directory. Fixtures in adapted `conftest.py`.
4. **Query corpus (`queries/`)** — Standalone SQL files (TPC-H queries, cross-driver joins). Mounted read-only, read by pytest and sent via pymysql. Editable without image rebuild.
5. **Orchestration scripts (`scripts/`)** — Build→ship→verify→retest loop, fast iteration paths. Ties the pieces together without dockerizing the test runner.

### Critical Pitfalls

The top 5 pitfalls that will cause the most pain if not addressed proactively:

1. **driver_url path mismatch (host vs container)** — `CREATE EXTERNAL CATALOG` fails because `driver_url` points to host paths that don't exist inside the container. **Avoid by:** Copying `.so` files into the image at build time; using fixed container-internal paths (`/opt/starrocks/drivers/`); switching conftest.py path sources when `DOCKER_COMPOSE=1`.

2. **127.0.0.1 vs Docker Compose service names** — Connection URIs like `postgresql://127.0.0.1:5432` work from the host but fail inside the StarRocks container (where 127.0.0.1 means the container itself, not the backend). **Avoid by:** Using Docker Compose service names (`sr-pg:5432`) for all cross-container URIs; reserving 127.0.0.1 only for the host→StarRocks pytest connection.

3. **priority_networks configuration race** — StarRocks FE/BE fails to bind to the correct Docker bridge network interface because `priority_networks` is not set at runtime. **Avoid by:** Patching `fe.conf`/`be.conf` in the entrypoint script with the container's runtime IP (via `hostname -i`), using a `/24` subnet mask. The `remote_table_verification` entrypoint.sh has the proven pattern.

4. **depends_on without healthcheck = flaky startup** — `docker compose up` returns before StarRocks or backends are actually ready, causing intermittent connection failures. **Avoid by:** Using `depends_on: condition: service_healthy` on all database services; configuring real healthchecks (`pg_isready`, `mysqladmin ping`, gRPC health probe); using generous `start_period` values.

5. **TPC-H DECIMAL column incompatibility in PostgreSQL ADBC** — The PostgreSQL ADBC driver returns DECIMAL as Arrow opaque extension types (not decimal128). StarRocks can't convert them, returning NULL for critical measurement columns (`l_extendedprice`, `l_discount`, etc.). **Avoid by:** Pre-creating VIEWs that CAST DECIMAL to DOUBLE in PostgreSQL init SQL, or using `DOUBLE PRECISION` instead of `DECIMAL` for the PostgreSQL TPC-H tables.

## Implications for Roadmap

Based on feature dependencies, architecture patterns, and pitfall avoidance, the suggested phase structure groups related requirements and respects dependency ordering:

### Phase 1: Docker Compose Foundation — "It Comes Up"

**Rationale:** Docker Compose self-containment is the foundation everything else depends on. Until the StarRocks container builds from a `.deb`, backend databases are Compose services (not subprocess calls), and pytest talks to the environment via Docker network service names, nothing else can proceed. The existing 35-test suite passes against locally-running StarRocks — this phase makes it pass against the Docker Compose environment instead. This is the highest-risk phase because it requires getting the container orchestration right (entrypoint script, healthchecks, priority_networks, service name DNS).

**Delivers:** A fully self-contained Docker Compose environment where `docker compose up --build` starts StarRocks (from `.deb` with ADBC drivers), PostgreSQL, MySQL, and FlightSQL/SQLite on a Docker bridge network. The existing 35-test suite passes against this environment (adapted conftest.py). `lib/docker_backends.py` and `lib/starrocks.py` are retired.

**Addresses features:**
- Docker Compose self-containment (**DC-01**)
- StarRocks container from shipped `.deb` (**DC-02**)
- Backend database provisioning in Compose mode (**DC-03** — basic 3-row test data, not TPC-H)
- Pytest conftest adapted to Docker Compose service names (**DC-04**)

**Avoids pitfalls:**
- Pitfall 1 (driver_url path mismatch) — drivers baked into image
- Pitfall 2 (127.0.0.1 vs service names) — conftest uses Docker DNS names
- Pitfall 3 (priority_networks race) — entrypoint patches at runtime
- Pitfall 4 (depends_on without healthcheck) — all services have `condition: service_healthy`
- Pitfall 6 (Init SQL before BE ready) — entrypoint waits for BE liveness
- Pitfall 7 (volume mount overwrites) — init SQL mounted correctly, certs extracted via `docker cp`
- Pitfall 10 (FlightSQL port confusion) — documented constants in conftest

### Phase 2: TPC-H Depth — "It Proves Federation"

**Rationale:** Once the Docker Compose foundation is solid, add the depth that makes this suite distinct: TPC-H schema+data in every backend, externalized SQL query corpus, and cross-driver JOIN verification. This phase leverages the Docker Compose foundation to prove the ADBC catalog layer handles production-grade SQL complexity across heterogeneous backends. The DECIMAL column pitfall must be addressed here — this is the phase where it bites.

**Delivers:** TPC-H schema and seed data loaded into all five backends (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB .db, SQLite .db). Standalone SQL query corpus in `queries/` directory. Test runner reads externalized query files, substitutes catalog/database names, executes, asserts results. Cross-driver JOIN tests run using Docker service names. PostgreSQL DECIMAL column issue resolved via VIEW-based CAST or DOUBLE schema.

**Uses stack elements:**
- PostgreSQL 16 init SQL (`docker-entrypoint-initdb.d/`)
- MySQL 8.0 init SQL (dialect-aware TPC-H DDL)
- sqlflite init SQL (SQLite dialect TPC-H)
- DuckDB/SQLite `.db` files generated by `generate_data.sh`

**Implements:**
- TPC-H query corpus (**DC-05**)
- Cross-driver join test corpus (**DC-06**)
- Query execution engine that maps query files to catalogs

**Addresses pitfalls:**
- Pitfall 5 (TPC-H DECIMAL column incompatibility) — resolved by VIEW CAST to DOUBLE

### Phase 3: Developer Experience — "It's a Joy to Use"

**Rationale:** The suite works, but it must be fast and pleasant for daily use. This phase automates the build→ship→verify→retest loop, adds structured failure diagnostics, and provides the CLI runner that makes the suite a single-command operation. These are all "nice to have" that significantly improve velocity and adoption. No dependencies on Phase 2 being TPC-H — the CLI runner works with any query corpus.

**Delivers:** `run-verify.sh` CLI that accepts `.deb` paths and orchestrates the full cycle (copy .deb → `docker compose up --build` → healthcheck wait → run tests → produce report → optional teardown). Log capture on failure extended to Compose logs from all backend services. Fast iteration path documented and optimized (reuse images, subset tests via pytest `-k`). Ship→verify→retest loop documented as an inner dev loop workflow.

**Addresses features:**
- Ship→verify→retest loop script (**DC-07**)
- Log capture on failure (extended to Compose logs) (**DC-08**)
- CLI runner (`run-verify.sh`) (**DC-09**)
- Fast iteration path (**DC-10**)

**Avoids pitfalls:**
- Pitfall 8 (stale container state) — CLI runner always offers `--clean` option
- Pitfall 9 (DEB cache inconsistency) — `--no-cache` flag available

### Phase Ordering Rationale

- **Docker Compose before everything.** Until Phase 1 works, Phase 2 data loading has no runtime environment. The foundation must be solid.
- **Basic data before TPC-H.** Phase 1 validates the Docker Compose pattern with small test data (3 rows). Phase 2 scales up to TPC-H. This reduces risk: if the Docker Compose pattern is broken, you discover it on simple data, not complex TPC-H schemas.
- **Functional correctness before developer experience.** Phases 1-2 prove the suite works. Phase 3 makes it pleasant. This prevents polishing a broken tool.
- **Pitfall prevention is front-loaded.** The most destructive pitfalls (driver_url, DNS, priority_networks, healthchecks) are all addressed in Phase 1. Later phases deal with data-level issues (DECIMAL) and operational polish (stale state, cache).

### Research Flags

**Phases likely needing deeper research during planning (`/gsd-research-phase`):**
- **Phase 2 (TPC-H Depth):** Cross-backend TPC-H SQL dialect portability. PostgreSQL, MySQL, and SQLite have different DDL syntax for TPC-H tables (e.g., `SERIAL` vs `INT AUTO_INCREMENT` vs `INTEGER PRIMARY KEY AUTOINCREMENT`). The DECIMAL→DOUBLE cast strategy needs validation — does `CAST(l_extendedprice AS DOUBLE PRECISION)` in a PostgreSQL VIEW actually return Arrow float64 through the ADBC driver? Query parameterization approach for catalog/database name substitution in externalized SQL files needs design.
- **Phase 1 (Docker Compose Foundation) partially:** The `entrypoint.sh` script is well-understood (pattern proven in `remote_table_verification`), but the exact `priority_networks` subnet and `SHOW BACKENDS` polling logic may need adaptation to this specific Docker network configuration. Low-risk research — spike if the pattern doesn't work on first try.

**Phases with standard patterns (skip `research-phase`, go straight to discuss→plan→execute):**
- **Phase 3 (Developer Experience):** Bash CLI scripting is a well-understood domain. The ship→verify→retest loop is a composition of existing commands (`docker compose`, `pytest`, `.deb` copy). No novel research needed.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All technology choices verified against multiple sources: Docker Compose specification (Context7), `remote_table_verification` reference implementation, existing test suite's `pyproject.toml`. PostgreSQL 16, MySQL 8.0, and sqlflite images are Docker Hub official builds with documented healthcheck patterns. |
| Features | HIGH | Feature landscape derived from existing 35-test suite, `remote_table_verification` reference project, StarRocks ADBC catalog API documentation (PROP-02..05, VAL-03..04), and PROJECT.md requirements. Priority matrix reflects actual test coverage and documented validation rules. |
| Architecture | HIGH | Architecture pattern (host pytest + Docker Compose + co-located FE/BE + Docker DNS) is directly proven in the `remote_table_verification` reference. Component boundaries, data flows, and anti-patterns are all validated against the reference implementation and Docker Compose specification. |
| Pitfalls | HIGH | All 10 pitfalls are sourced from the reference project's documented issues, Docker official docs, existing `lib/` code patterns, and StarRocks configuration documentation. Each pitfall has a concrete prevention strategy with example code. The "Looks Done But Isn't" checklist was derived from reference project debugging sessions. |

**Overall confidence: HIGH**

The single reference project (`remote_table_verification`) provides a working proof of the core pattern. Combined with official Docker Compose documentation (Context7-verified), StarRocks configuration docs, and the existing working test suite, the research is grounded in proven practice, not speculation.

### Gaps to Address

- **TPC-H SQL dialect portability:** The exact DDL differences between PostgreSQL, MySQL, and SQLite/Flightsql for TPC-H tables need to be resolved during Phase 2 planning. The research identifies this as a gap but doesn't provide the final DDL files. Mitigation: spike during Phase 2 discuss/plan — write one backend's init SQL and port it to the other two.
- **PostgreSQL DECIMAL→DOUBLE cast validation:** Research identifies the DECIMAL Arrow opaque extension type issue but doesn't confirm that `CAST(... AS DOUBLE PRECISION)` in a PostgreSQL VIEW actually remedies the problem end-to-end through the ADBC driver → StarRocks pipeline. Mitigation: first test in Phase 2 should validate this with a small query before loading full TPC-H.
- **MySQL ADBC driver TLS support:** The features research mentions extending TLS verification to MySQL "if the ADBC MySQL driver supports TLS options." Whether the MySQL ADBC driver exposes TLS connection parameters (and which ones) is unverified. Mitigation: defer to Phase 2 planning — research may yield "not supported" and TLS remains PostgreSQL/FlightSQL only.
- **StarRocks BE `SHOW BACKENDS` liveness polling timing:** The research references a 5-second sleep + 30-second polling loop from the reference project. The exact timing may need tuning for different host specs. Mitigation: make the polling timeout configurable via environment variable.

## Sources

### Primary (HIGH confidence)
- **`/home/mete/coding/remote_table_verification/`** — Proven reference architecture: Dockerfile from DEB, `docker-compose.yml` with named network, `depends_on` with healthchecks, `entrypoint.sh` with priority_networks patching and BE readiness loop, host pytest pattern, TPC-H init SQL. Directly adapted for this project.
- **`/home/mete/coding/opensource/adbc_verification/`** — Existing 35-test suite (`tests/`, `conftest.py`, `lib/`, `pyproject.toml`). Validates per-driver ADBC catalog operations, cross-driver joins, TLS, pass-through, and negative cases. The baseline this milestone enhances.
- **Context7: `/docker/compose`** — Compose Specification format (no `version` key), `depends_on` long syntax with `condition: service_healthy`, healthcheck configuration including `start_period`, `docker compose up --wait` CI integration.
- **Context7: `/docker/docs`** — Container lifecycle, bind mount behavior (directory-level replacement), `/docker-entrypoint-initdb.d/` initialization pattern for PostgreSQL/MySQL.
- **Docker Hub official images** — `postgres:16` (`pg_isready` healthcheck), `mysql:8.0` (`mysqladmin ping` healthcheck), `voltrondata/sqlflite:latest` (FlightSQL interface, port 31337).

### Secondary (MEDIUM confidence)
- **StarRocks documentation (`/websites/starrocks_io`)** — `priority_networks` configuration, `CREATE EXTERNAL CATALOG` API, Arrow Flight dual-port architecture (FE:9408 query service, BE:9419 data transfer).
- **Apache Arrow ADBC documentation (`/apache/arrow-adbc`)** — Driver shared library loading, TOML manifest format, FlightSQL connection options (`adbc.flight.sql.client_option.*`).

### Tertiary (LOW confidence — needs validation)
- **MySQL ADBC driver TLS capabilities** — Not documented in accessible sources. Whether the MySQL ADBC driver supports `sslmode` or equivalent TLS properties is unknown. Flagged for Phase 2 research.

---

*Research completed: 2026-04-27*
*Ready for roadmap: yes*
