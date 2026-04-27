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

- [ ] **DC-07**: Ship → verify → retest loop script: rebuild DEB in StarRocks repo, copy into `docker/`, `docker compose up --build`, run tests, report results. One command for the full cycle
- [ ] **DC-08**: Log capture on failure that pulls container logs (FE, BE, all backend services) into the test report. Extended from existing `capture_on_failure` fixture
- [ ] **DC-09**: CLI runner (`run-verify.sh`) that accepts .deb paths and orchestrates the full test cycle (up with healthcheck wait, test, report, optional down)
- [ ] **DC-10**: Fast iteration path: documented subset test mode (`pytest -k flightsql`) combined with container reuse (reuse running Compose services when DEB hasn't changed)

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

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-27*
*Last updated: 2026-04-27 after roadmap creation*
