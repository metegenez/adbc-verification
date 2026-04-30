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
- ✓ **BENCH-01..BENCH-08**: MySQL JDBC vs ADBC benchmark CLI with argparse, warmup/measurement loop, EXPLAIN ANALYZE parsing, ASCII table output, AVG/GEOMEAN summaries — Validated in Phase 03
- ✓ **FS-SR-01..FS-SR-09**: Second StarRocks instance (sr-external) on Compose with TPC-H SF1 native tables, ADBC FlightSQL catalog `sr_flightsql_starrocks` over `grpc://sr-external:9408`, 4-scenario test module, canonical `queries/tpch/` consolidating 44 per-backend duplicates, DuckDB tpch SF1 generator, dead `lib/` cleanup — Validated in Phase 04

### Active

*(none — all active requirements validated in Phase 01/02/03/04)*

### Out of Scope

- CI/CD pipeline integration — local first; CI can be layered later
- ARM/AArch64 builds — x86_64 only for now
- OAuth or Kerberos authentication — username/password only
- External test data creation scripts — TPC-H data generation handled within Docker Compose startup

## Context

All four phases complete via GSD workflows — milestone v1.0 closed at 11/11 plans:
- **Phase 01**: Docker Compose verification suite — 5 backends, 35 tests, CLI runner (`run-verify.py`)
- **Phase 02**: TPC-H SF1 data (~900 MB) for PostgreSQL and MySQL, 44 TPC-H query files, data generators
- **Phase 03**: MySQL JDBC vs ADBC benchmark CLI (`benchmark/mysql-jdbc-vs-adbc.py`) with EXPLAIN ANALYZE timing, ASCII comparison table, and smoke tests
- **Phase 04**: Second StarRocks instance (`sr-external`) over Arrow Flight at `grpc://sr-external:9408`; canonical `queries/tpch/q01..q22.sql` corpus with `{catalog}.{db}` placeholders consumed by `tests/test_queries.py` cross-product loader (`CANONICAL_BACKENDS`, `CANONICAL_SKIPS`); DuckDB-based SF1 generator; dead `lib/` cleanup. Suite now reports 98 passed / 20 skipped (17 postgres-numeric + 2 DuckDB :memory: + 1 sqlflite-join) / 0 failed.

## Constraints

- **Docker**: Docker and Docker Compose v2 must be available
- **DEB source**: StarRocks `.deb` must exist at `docker/starrocks-fe_*.deb` and `docker/starrocks-be_*.deb`
- **Architecture**: x86_64 only (DEBs are amd64)
- **Drivers**: ADBC driver `.so` files must be available on the host for embedding into the StarRocks container image
- **JAR**: MySQL Connector/J JAR fetched via `docker/fetch-jdbc-jar.sh` (one-time, placed in `docker/drivers/`)
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
| JDBC catalog property key is `user` (NOT `username`) | ADBC uses `username`, JDBC uses `user` per StarRocks docs | Implemented — `create_jdbc_catalog` docstring calls out the distinction |
| EXPLAIN ANALYZE timing over client-side wall-clock | Server-side timing is deterministic and comparable across catalogs | Implemented — `benchmark/explain_parser.py` parses StarRocks plan output |
| MySQL Connector/J 9.3.0 as JDBC driver | Latest 9.x, uses modern `com.mysql.cj.jdbc.Driver` | Implemented — `docker/fetch-jdbc-jar.sh` downloads from Maven Central |

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
*Last updated: 2026-04-30 after Phase 04 completion*
