# StarRocks ADBC Built-In Verification Suite

## What This Is

A Docker Compose-based end-to-end verification suite for the StarRocks ADBC catalog stack. Ships a StarRocks DEB into a container alongside a fleet of backend data sources (PostgreSQL, MySQL, FlightSQL, DuckDB, SQLite), then runs TPC-H and cross-driver join queries against them through the StarRocks ADBC catalog layer. The entire environment is self-contained in Docker Compose — no locally running StarRocks required. SQL test files live outside the containers so they can be versioned and iterated on independently.

## Core Value

**verify before merge** — catch ADBC catalog regressions by running the full verification suite against a freshly shipped StarRocks DEB in a Docker Compose environment, enabling the fast fix → build → ship → retest loop without manual setup.

## Requirements

### Validated

- ✓ pytest test suite with 35 tests covering SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL, cross-joins, and negative cases — existing
- ✓ ADBC driver registry reads .so paths from `~/.config/adbc/drivers/*.toml` — existing
- ✓ Docker backends (MySQL, PostgreSQL, SQLite/FlightSQL) via subprocess — existing
- ✓ TLS support for FlightSQL — existing
- ✓ REQ‑TLS for PostgreSQL — existing
- ✓ Catalog lifecycle helpers (CREATE/DROP EXTERNAL CATALOG) — existing

### Active

- [ ] **DC-01**: Docker Compose file that packages StarRocks (from shipped DEB) + all backend data sources as named services
- [ ] **DC-02**: StarRocks container built from a shipped .deb, with all ADBC drivers pre-installed inside the container
- [ ] **DC-03**: Backend data containers (PostgreSQL, MySQL, FlightSQL/SQLite) with TPC-H schema and data pre-loaded at startup
- [ ] **DC-04**: Pytest conftest adapted to use Docker Compose service names (container networking) instead of host ports
- [ ] **DC-05**: TPC-H query corpus as standalone SQL files in a `queries/` directory, runnable against catalogs defined by environment variables or per-driver config
- [ ] **DC-06**: Cross-driver join test corpus (e.g., FlightSQL ↔ PostgreSQL joins via StarRocks internal federation)
- [ ] **DC-07**: Ship → verify → retest loop script: rebuild DEB, copy into docker/, `docker compose up --build`, run tests
- [ ] **DC-08**: Log capture on failure that pulls container logs (FE, BE, backend) into the test report
- [ ] **DC-09**: CLI runner that accepts a DEB path and orchestrates the full test cycle (up, test, down)
- [ ] **DC-10**: Fast iteration path: copy .deb to docker/, docker compose up -d --build, run subset of tests relevant to the change

### Out of Scope

- CI/CD pipeline integration — local first; CI can be layered later
- ARM/AArch64 builds — x86_64 only for now
- OAuth or Kerberos authentication — username/password only
- Performance benchmarking — functional correctness only
- External test data creation scripts — TPC-H data generation handled within Docker Compose startup

## Context

The existing test suite (`tests/`, `conftest.py`, `lib/`) works against a locally running `STARROCKS_HOME` and individually managed Docker containers. It requires manual StarRocks startup, hardcoded host ports, and doesn't support the build→ship→test cycle. The `remote_table_verification` project at `/home/mete/coding/remote_table_verification/` demonstrates the proven pattern: Docker Compose with `rtv-main` (StarRocks from DEB), backend services on a Docker network, and pytest run from host connecting to exposed MySQL port. This project adapts that pattern here but goes further: all backend databases get TPC-H preloaded, SQL queries are externalized, and the full toolchain supports the inner dev loop.

## Constraints

- **Docker**: Docker and Docker Compose v2 must be available
- **DEB source**: StarRocks `.deb` must exist at `docker/starrocks-fe_*.deb` and `docker/starrocks-be_*.deb`
- **Architecture**: x86_64 only (DEBs are amd64)
- **Drivers**: ADBC driver `.so` files must be available on the host for embedding into the StarRocks container image
- **Python**: Python 3.11+, pytest, pymysql (already set up in `.venv`)
- **Network**: Docker Compose internal network; host only needs access to the StarRocks MySQL port (published)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Docker Compose instead of separate `docker run` calls | Single command to bring up/down the entire environment; service discovery via DNS on internal network | — Pending |
| StarRocks from DEB in Dockerfile, not from source build in container | Matches the ship→test loop; faster iteration | — Pending |
| SQL queries as standalone files outside Docker Compose | Editable/versionable independently of container images | — Pending |
| TPC-H as query corpus | Standard benchmark; meaningful cross-driver queries | — Pending |
| Host runs pytest against Docker Compose exposed port | Simple; no need for pytest-in-docker | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-27 after initialization*
