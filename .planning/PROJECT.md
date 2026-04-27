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
- ✓ **DC-01**: Docker Compose file with 5 services on sr-net bridge network — Validated in Phase 01
- ✓ **DC-02**: StarRocks container from ubuntu:24.04 .deb with all 5 ADBC drivers baked in — Validated in Phase 01
- ✓ **DC-03**: Backend data containers with TPC-H schema and data pre-loaded at startup — Validated in Phase 01
- ✓ **DC-04**: Pytest conftest adapted for Docker Compose service names and fixed driver paths — Validated in Phase 01
- ✓ **DC-05**: TPC-H query corpus as standalone SQL files in `queries/` directory — Validated in Phase 01
- ✓ **DC-06**: Cross-driver join test corpus (SQLite↔PostgreSQL federation) — Validated in Phase 01
- ✓ **DC-07**: Ship→verify→retest loop via `run-verify.py` — Validated in Phase 01
- ✓ **DC-08**: Log capture on failure pulling container logs into test report — Validated in Phase 01
- ✓ **DC-09**: CLI runner accepting DEB path and orchestrating full test cycle — Validated in Phase 01
- ✓ **DC-10**: Fast iteration path: `pytest -k` with running containers — Validated in Phase 01

### Active

*(none — all active requirements validated in Phase 01)*

### Out of Scope

- CI/CD pipeline integration — local first; CI can be layered later
- ARM/AArch64 builds — x86_64 only for now
- OAuth or Kerberos authentication — username/password only
- Performance benchmarking — functional correctness only
- External test data creation scripts — TPC-H data generation handled within Docker Compose startup

## Context

Phase 01 complete — Docker Compose verification suite built. The project now contains:
- `docker/` with Docker Compose (5 services), Dockerfile, entrypoint, init SQL, pre-baked data, TLS certs
- `conftest.py` refactored for Docker Compose (env var config, fixed driver paths, compose log capture)
- `tests/` adapted for Docker DNS service names (sr-postgres, sr-mysql, sr-flightsql)
- `queries/` with TPC-H SQL files per driver and cross-driver federation queries
- `run-verify.py` CLI runner for the full ship→verify→retest loop
- `README.md` with setup, fast iteration, and troubleshooting docs

All 17 requirements (6 legacy + DC-01 through DC-10 + VAL-01 through VAL-07) validated in Phase 01.

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
| Docker Compose instead of separate `docker run` calls | Single command to bring up/down the entire environment; service discovery via DNS on internal network | Implemented — 5 services on `sr-net` bridge network |
| StarRocks from DEB in Dockerfile, not from source build in container | Matches the ship→test loop; faster iteration | Implemented — `docker/` contains Dockerfile with `.deb` install |
| SQL queries as standalone files outside Docker Compose | Editable/versionable independently of container images | Implemented — `queries/` directory with per-driver SQL files |
| TPC-H as query corpus | Standard benchmark; meaningful cross-driver queries | Implemented — 8-table TPC-H schema with seed data across all backends |
| Host runs pytest against Docker Compose exposed port | Simple; no need for pytest-in-docker | Implemented — `conftest.py` connects to `STARROCKS_HOST:STARROCKS_PORT` |
| Driver paths as constants in conftest.py | Deterministic; no TOML resolution at runtime | Implemented — `/opt/starrocks/drivers/` fixed paths |
| Containers stay running by default after tests | Fast re-test iteration without rebuild | Implemented — `run-verify.py --keep` (default) |

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
*Last updated: 2026-04-27 after Phase 01 completion*
