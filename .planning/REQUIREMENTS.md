# Requirements: StarRocks ADBC Built-In Verification Suite

**Defined:** 2026-04-27
**Core Value:** verify before merge — catch ADBC catalog regressions by running the full verification suite against a freshly shipped StarRocks DEB in a Docker Compose environment

## v1 Requirements

Requirements for the Docker Compose transformation. Each maps to a roadmap phase.

### Docker Compose Foundation

- [x] **DC-01
**: Docker Compose file that packages StarRocks (from shipped DEB) + all backend data sources as named services on a Docker bridge network
- [x] **DC-02
**: StarRocks container built from shipped `.deb`, with FE+BE co-located, all five ADBC drivers pre-installed at `/opt/starrocks/drivers/`, and a working entrypoint script
- [x] **DC-03
**: Backend data containers (PostgreSQL, MySQL, FlightSQL/SQLite) with test data pre-loaded at startup via init SQL volume mounts. DuckDB and SQLite `.db` files baked into the StarRocks container image
- [x] **DC-04
**: Pytest conftest adapted to use Docker Compose service names for cross-container URIs instead of host-loopback ports. `lib/docker_backends.py` and `lib/starrocks.py` retired in favor of Compose service management

### TPC-H Depth

- [x] **DC-05
**: TPC-H schema and seed data loaded into all five backends (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB .db, SQLite .db). Queries stored as standalone SQL files in `queries/` directory, runnable against catalogs with driver-specific catalog mapping
- [x] **DC-06
**: Cross-driver join test corpus adapted to Docker service names. Queries that JOIN tables across different ADBC backends (e.g., `sr_flightsql.tpch.orders` JOIN `sr_postgres.tpch.lineitem`) run end-to-end

### Developer Experience

- [x] **DC-07
**: Ship → verify → retest loop script: rebuild DEB in StarRocks repo, copy into `docker/`, `docker compose up --build`, run tests, report results. One command for the full cycle
- [x] **DC-08
**: Log capture on failure that pulls container logs (FE, BE, all backend services) into the test report. Extended from existing `capture_on_failure` fixture
- [x] **DC-09
**: CLI runner (`run-verify.sh`) that accepts .deb paths and orchestrates the full test cycle (up with healthcheck wait, test, report, optional down)
- [x] **DC-10
**: Fast iteration path: documented subset test mode (`pytest -k flightsql`) combined with container reuse (reuse running Compose services when DEB hasn't changed)

### Multi-Driver Validation (Existing — Adapted)

These are the inherited test modules from the existing suite. They must pass against the Docker Compose environment after conftest adaptation.

- [x] **VAL-01
**: SQLite catalog lifecycle, data round-trip, error paths (6 tests)
- [x] **VAL-02
**: DuckDB catalog lifecycle, data round-trip, entrypoint, pass-through (4 tests)
- [x] **VAL-03
**: MySQL catalog lifecycle, data round-trip, SHOW TABLES, errors, cross-join (5 tests)
- [x] **VAL-04
**: PostgreSQL catalog lifecycle, data round-trip, SHOW TABLES, errors, TLS, passthrough (6 tests)
- [x] **VAL-05
**: FlightSQL catalog lifecycle, data round-trip, TLS, auth, passthrough (5 tests)
- [x] **VAL-06
**: Cross-driver JOIN tests across heterogeneous backends (2 tests)
- [x] **VAL-07
**: Negative/validation error path coverage for all PROP/VAL rules (7 tests)

### FlightSQL → External StarRocks (Phase 4)

These cover the new `sr_flightsql_starrocks` catalog backed by an external StarRocks instance (`sr-external`) populated with TPC-H SF1 native tables, plus the cleanup work that consolidates the TPC-H corpus into a single canonical home and retires dead `lib/` files. The existing sqlflite FlightSQL path (VAL-05) coexists.

- [x] **FS-SR-01
**: `sr-external` Compose service exists, builds from the same Dockerfile as sr-main, publishes no host ports, mounts `./data/sf1/` read-only and `./init/sr-external/` for init SQL, and reports healthy via the same `mysql -uroot -h127.0.0.1 -P9030 -e "SELECT 1"` healthcheck shape (D-01, D-02, D-03)
- [x] **FS-SR-02
**: TPC-H schema is created in sr-external under database `tpch`, and all 8 tables (region, nation, supplier, part, partsupp, customer, orders, lineitem) are loaded from the canonical SF1 CSVs via `INSERT INTO tpch.<table> SELECT * FROM FILES('file:///opt/starrocks/data/sf1/<table>.csv', 'format'='csv', ...)` (D-05, D-07, D-08)
- [x] **FS-SR-03
**: Init is idempotent across both cold (`down -v && up`) and warm (`restart`) boots — every init SQL file uses `CREATE DATABASE IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / `TRUNCATE TABLE` so re-running the init loop converges to the same row counts (D-04, RESEARCH Pitfall 8)
- [x] **FS-SR-04
**: `tests/test_flightsql_starrocks.py` ships 4 scenarios — lifecycle, data, wrong-password, ADBC pass-through — and they all pass against a `sr_flightsql_starrocks` catalog at `grpc://sr-external:9408` with `username=root` / `password=""` (D-11, D-13, D-15, D-16)
- [x] **FS-SR-05
**: All 22 canonical TPC-H query files under `queries/tpch/q01.sql..q22.sql` execute via `tests/test_queries.py` against the `sr_flightsql_starrocks` catalog and return correct row counts (D-09, D-10, RESEARCH Pitfall 6 — adopt mysql counts, NOT postgres counts)
- [x] **FS-SR-06
**: The pre-existing sqlflite path coexists — `tests/test_flightsql.py` (5 tests against `sr-flightsql` / `sr-flightsql-tls`) and `queries/flightsql/` (2 query files) continue to pass with no regression after sr-external lands (D-12, D-14)
- [x] **FS-SR-07
**: Dead/superseded `lib/` files are deleted — `lib/docker_backends.py`, `lib/starrocks.py`, `lib/tls.py`, and `lib/driver_registry.py` are removed (post-Phase-1 they're no longer imported by `conftest.py` or any test). `lib/` retains only `__init__.py` and `catalog_helpers.py`.
- [x] **FS-SR-08
**: `docker/generate-sf1-data.py` is rewritten to use the canonical DuckDB `tpch` extension (`INSTALL tpch; LOAD tpch; CALL dbgen(sf=1); COPY <table> TO '<path>' (FORMAT CSV, HEADER TRUE, DELIMITER ',')`). Generator file is ≤50 lines, deterministic, produces LF-terminated CSVs with header rows at the canonical SF1 row counts (region=5, nation=25, supplier=10000, part=200000, partsupp=800000, customer=150000, orders=1500000, lineitem=6001215) — no hand-rolled mock data generation. Header rows are required by all consumers (postgres `\COPY ... HEADER true`, mysql `LOAD DATA ... IGNORE 1 ROWS`, sr-external `csv.skip_header='1'`).
- [x] **FS-SR-09
**: `queries/tpch/q01.sql..q22.sql` is the single canonical TPC-H query home. The 44 per-backend duplicates `queries/mysql/03-q*.sql` and `queries/postgres/03-q*.sql` are deleted. Canonical files use `{catalog}.{db}` template substitution at test-collection time, with the per-backend skip manifest (`CANONICAL_SKIPS`) living in `tests/test_queries.py` and the per-backend mapping in `CANONICAL_BACKENDS` (per `04-CANONICAL-SPEC.md`).

## v2 Requirements

Deferred to future release. Not in current roadmap.

### Developer Experience Enhancements

- **DX-01**: Structured JSON report with per-driver pass/fail summary, timing, and log attachments
- **DX-02**: CI/CD pipeline integration (GitHub Actions) invoking the CLI runner
- **DX-03**: Automatic DEB build trigger — watch StarRocks repo for changes, rebuild, ship, retest
- **DX-04**: Multi-StarRocks-version testing — test against multiple DEB versions to bisect regressions

### Extended Coverage

- **DX-05**: MySQL ADBC driver TLS verification (pending driver capability research)
- **DX-06**: OAuth/Kerberos authentication path testing
- **DX-07**: TPC-H full query set (all 22 queries validated against known results)
- **DX-08**: Stress/concurrency test — multiple simultaneous connections to same catalog

## Out of Scope

| Feature | Reason |
|---------|--------|
| Performance benchmarking | Wall-clock timing in Docker is noisy; separate concern requiring controlled environments |
| In-Docker pytest execution | Adds complexity, slows iteration; host pytest is the proven pattern |
| Real data volume testing (100M+ rows) | Correctness suite only needs seed data; scale testing is a separate concern |
| OAuth / Kerberos authentication | Requires external infrastructure; breaks self-contained Compose model |
| Multi-architecture builds (ARM/AArch64) | StarRocks .deb packages are amd64 only |
| Real-time test progress dashboard | CLI tool, not a web app; pytest terminal output suffices |
| Rollback/state checkpointing | Docker Compose down/up provides clean state; data re-seeds in seconds |
| Interactive test debugging mode | pytest's native `--pdb` already handles this |

## Traceability

| Requirement | Phase | Plan | Status |
|-------------|-------|------|--------|
| DC-01 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| DC-02 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| DC-03 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| DC-04 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| DC-05 | Phase 1: Docker Compose Verification Suite | 01-02 | Pending |
| DC-06 | Phase 1: Docker Compose Verification Suite | 01-02 | Pending |
| DC-07 | Phase 1: Docker Compose Verification Suite | 01-03 | Pending |
| DC-08 | Phase 1: Docker Compose Verification Suite | 01-03 | Pending |
| DC-09 | Phase 1: Docker Compose Verification Suite | 01-03 | Pending |
| DC-10 | Phase 1: Docker Compose Verification Suite | 01-03 | Pending |
| VAL-01 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| VAL-02 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| VAL-03 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| VAL-04 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| VAL-05 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| VAL-06 | Phase 1: Docker Compose Verification Suite | 01-02 | Pending |
| VAL-07 | Phase 1: Docker Compose Verification Suite | 01-01 | Pending |
| FS-SR-01 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-01 | Complete |
| FS-SR-02 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-01 | Complete |
| FS-SR-03 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-01 | Complete |
| FS-SR-04 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-02 | Complete |
| FS-SR-05 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-02 | Complete |
| FS-SR-06 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-02 | Complete |
| FS-SR-07 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-04 | Complete |
| FS-SR-08 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-05 | Complete |
| FS-SR-09 | Phase 4: FlightSQL TPC-H Queries Against External StarRocks | 04-05 | Complete |

**Coverage:**
- v1 requirements: 26 total (17 Docker Compose + 9 FlightSQL→StarRocks)
- Mapped to phases: 26
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-27*
*Last updated: 2026-04-30 after Phase 4 completion (all FS-SR-* requirements satisfied)*
