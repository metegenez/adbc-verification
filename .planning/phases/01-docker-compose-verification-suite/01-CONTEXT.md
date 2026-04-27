# Phase 1: Docker Compose Verification Suite - Context

**Gathered:** 2026-04-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Self-contained Docker Compose verification environment: `docker compose up --build` starts StarRocks from shipped `.deb` with all 5 ADBC drivers alongside backend databases (PostgreSQL, MySQL, FlightSQL/SQLite) on a Docker bridge network. All 35 existing tests pass. TPC-H queries and cross-driver JOINs execute correctly. `run-verify.py` orchestrates the full build→ship→verify→retest cycle with structured failure diagnostics.

This phase covers all 3 plans (01-01 Foundation, 01-02 TPC-H Depth, 01-03 Developer Experience) since they are interlocked — Foundation creates the containers and conftest, TPC-H loads data into them, Developer Experience wraps both in tooling.

</domain>

<decisions>
## Implementation Decisions

### Compatibility Mode
- **D-01:** Hard replace. Retire `lib/docker_backends.py` entirely. Simplify `lib/starrocks.py` to a pymysql connect function only (no subprocess FE/BE startup, no log tailing). Replace `STARROCKS_HOME` env var with a connection address (`STARROCKS_HOST` + `STARROCKS_PORT` or compose-mode flag). No dual-mode — Docker Compose is the only path.

### Container Topology & Assets
- **D-02:** FE+BE co-located in a single container (`sr-main`). One Dockerfile, one entrypoint that starts FE then BE sequentially.
- **D-03:** ADBC driver `.so` files baked into the StarRocks image at build time via `COPY docker/drivers/ /opt/starrocks/drivers/`. Driver paths are fixed container-internal paths (e.g., `/opt/starrocks/drivers/libadbc_driver_sqlite.so`). No volume mounts.
- **D-04:** SQLite and DuckDB `.db` test files baked into the StarRocks image via `COPY docker/data/ /opt/starrocks/data/`. Fixed container paths. No volume mounts.

### Data Loading Strategy
- **D-05:** TPC-H schema + data loaded into PostgreSQL, MySQL, and FlightSQL/sqlflite backend containers at startup via init scripts (mounted into `docker-entrypoint-initdb.d/` or equivalent). No data baking into backend images — init scripts are volume-mounted so they can be edited without rebuild.
- **D-06:** TPC-H Scale Factor 1 (~1GB total) for all backends. Full TPC-H query set (22 queries) supported. Data generation happens as part of container build (e.g., `tpch-kit` in Dockerfile or pre-generated CSV/SQL in `docker/init/`).

### CLI Runner & Dev Loop
- **D-07:** `run-verify.py` — Python CLI (argparse). Accepts `.deb` paths, orchestrates: copy .deb → `docker compose up --build` → wait for health → `pytest tests/ -v` → report → (optional) down.
- **D-08:** Containers are left running after tests complete. No auto-cleanup. User runs `docker compose down` manually. This enables re-running tests without rebuild.
- **D-09:** Log capture on failure: capture StarRocks FE/BE logs via `docker compose logs sr-main --tail=50`, plus print `docker compose logs --tail=50` for all services. No per-service smart routing — simple and sufficient.
- **D-10:** Query files organized in per-driver directories: `queries/sqlite/`, `queries/postgres/`, `queries/mysql/`, `queries/flightsql/`, `queries/duckdb/`. Each directory contains TPC-H `.sql` files. Cross-join queries in `queries/cross-join/`. Directory name maps directly to a driver/catalog.
- **D-11:** Fast iteration path: `docker compose up -d` (reuses running containers if DEB hasn't changed), then `pytest -k <filter>`. No special CLI flag for subset mode — documented `pytest -k` is sufficient.

### the agent's Discretion
- Exact Dockerfile structure (base image, multi-stage or single-stage)
- Entrypoint script implementation details (FE startup flags, `priority_networks` patching, BE registration polling)
- Conftest fixture refactoring specifics (how `capture_on_failure` calls `docker compose logs`)
- TPC-H data generation mechanism (in-Dockerfile via tpch-kit, pre-generated SQL in `docker/init/`, or Python script)
- TLS certificate handling for FlightSQL and PostgreSQL (pre-generated vs runtime generation in entrypoint)
- `run-verify.py` report format (plain text, JSON, or both)
- Dockerfile for FlightSQL/sqlflite (single or separate TLS/non-TLS services)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Docker Compose & StarRocks
- `.planning/PROJECT.md` — Key Decisions table: Docker Compose approach, StarRocks from .deb, SQL queries externalized, host pytest runner
- `.planning/REQUIREMENTS.md` — DC-01 through DC-10 (Docker Compose requirements), VAL-01 through VAL-07 (validation requirements), traceability table

### Existing Code (read before refactoring)
- `conftest.py` — Session fixtures: sr_conn, driver paths, Docker backend ports, capture_on_failure. Will be adapted for Compose service names and Docker-internal paths.
- `lib/catalog_helpers.py` — `create_adbc_catalog()`, `drop_catalog()`, `show_catalogs()`, `execute_sql()`. Unchanged — works with any URI.
- `lib/starrocks.py` — `ensure_starrocks_running()`, `tail_log()`. To be simplified to connect-only + `docker compose logs`.
- `lib/docker_backends.py` — Container lifecycle. To be entirely retired.
- `lib/driver_registry.py` — TOML-based driver path resolution. Runtime paths replaced by container-internal constants. TOML parsing may still be useful at build time for copying .so files.
- `lib/tls.py` — FlightSQL TLS container + cert extraction. To be adapted for Compose service.

### Reference Implementation
- `/home/mete/coding/remote_table_verification/` — Proven pattern: Docker Compose with StarRocks from DEB, backend services on Docker network, pytest from host. This project extends that pattern with all 5 ADBC drivers and TPC-H depth.

### StarRocks Build & Ship
- `ship-starrocks` skill — Builds StarRocks FE+BE from source, packages as .deb. The `run-verify.py` CLI calls this skill's output path convention.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `lib/catalog_helpers.py`: Pure SQL functions (create_adbc_catalog, drop_catalog, execute_sql) — completely agnostic to container topology. 100% preserved.
- All 35 test assertions in `tests/test_*.py`: Business logic unchanged. Only URIs and driver paths change.
- `pyproject.toml`: Dependencies and pytest markers stay identical.
- `capture_on_failure` fixture pattern: Autouse hook stays; only log sources change from file reads to `docker compose logs`.

### Established Patterns
- Session-scoped fixtures with yield/teardown for cleanup
- `try: ... finally: drop_catalog()` pattern for guaranteed catalog cleanup
- Module-level fixtures for test data seeding (to be replaced by init scripts)
- Credential values (`testuser/testpass`, `root/testpass`) — preserved, delivered via Compose env vars

### Integration Points
- Host pytest → StarRocks MySQL port (published from Compose, still 9030)
- StarRocks BE → backend databases (now via Docker DNS: `sr-pg:5432`, `sr-mysql:3306`, `sr-flightsql:31337`)
- StarRocks BE → ADBC drivers (now container-internal paths: `/opt/starrocks/drivers/`)
- StarRocks BE → SQLite/DuckDB .db files (now container-internal paths: `/opt/starrocks/data/`)

### What Gets Retired
| Retired | Replaced By |
|---|---|
| `lib/docker_backends.py` (all) | `docker-compose.yml` services + healthchecks |
| `lib/starrocks.py` `ensure_starrocks_running()` (subprocess) | `docker compose up` |
| `lib/starrocks.py` `tail_log()` (file read) | `docker compose logs` |
| `STARROCKS_HOME` env var | `STARROCKS_HOST`/`STARROCKS_PORT` or compose-mode flag |
| Module `docker exec` data fixtures | `/docker-entrypoint-initdb.d/` init scripts |
| Module `sqlite3` subprocess seeding | Pre-baked `.db` files in image |
</code_context>

<specifics>
## Specific Ideas

- StarRocks container should follow the pattern from `/home/mete/coding/remote_table_verification/` — single DEB-based container, similar entrypoint flow
- User chose Python CLI over bash for better error handling and shared config with conftest
- No auto-cleanup — containers stay up for debugging between test runs
- Per-driver query directories keep things simple and explicit — no indirection through config files

</specifics>

<deferred>
## Deferred Ideas

- CI/CD pipeline integration (GitHub Actions) — v2 requirement, out of scope
- Bare-metal mode fallback — explicitly rejected; hard replace chosen
- Performance benchmarking — out of scope (Docker wall-clock timing is noisy)
- OAuth/Kerberos authentication — out of scope (breaks self-contained model)

</deferred>

---

*Phase: 01-docker-compose-verification-suite*
*Context gathered: 2026-04-27*
