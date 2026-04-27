# Feature Research: StarRocks ADBC Built-In Verification Suite

**Domain:** Database connector verification suites (ADBC catalog integration testing)
**Researched:** 2026-04-27
**Confidence:** HIGH

## Feature Landscape

This suite verifies that StarRocks' ADBC catalog layer correctly federates queries across
heterogeneous backend databases (PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB). It answers:
*"Does the ADBC connector work end-to-end for each driver, including cross-driver federation?"*

Research sources: the existing 35-test suite in this repo, the `remote_table_verification`
reference project at `/home/mete/coding/remote_table_verification/` (which provides the
proven Docker Compose pattern), the StarRocks ADBC catalog API (PROP-02..05, VAL-03..04
validation rules documented in test files), and general database test suite conventions.

---

### Table Stakes (Users Expect These)

Features users assume exist. Missing any of these = suite feels broken or incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Per-driver test modules** | One test file per ADBC driver type (SQLite, DuckDB, MySQL, PostgreSQL, FlightSQL). Users run `pytest tests/ -k "sqlite"` and expect only SQLite tests. Marker-based filtering (`@pytest.mark.sqlite`) already supports this. | LOW | Existing: `test_sqlite.py`, `test_duckdb.py`, `test_mysql.py`, `test_postgres.py`, `test_flightsql.py` |
| **Catalog lifecycle testing** | Every test follows CREATE EXTERNAL CATALOG → query → DROP CATALOG. The fundamental ADBC operation. Users expect creation, metadata discovery (SHOW CATALOGS, SHOW DATABASES, SHOW TABLES), and teardown to work for every driver. | LOW | Already implemented in all test modules. `catalog_helpers.py` provides `create_adbc_catalog()`, `drop_catalog()`, `show_catalogs()`. |
| **Data round-trip verification** | Seed test data into backend, SELECT through StarRocks ADBC catalog, assert correct rows, column values, and ordering. The core correctness invariant — if data doesn't round-trip, nothing else matters. | LOW | Existing: 3-row test_data fixture in every driver module. Rows verified by id, name, and floating-point value with tolerance. |
| **Backend database provisioning** | Real database instances provided by Docker containers (MySQL 8.0, PostgreSQL 16, sqlflite). Users expect `pytest` to Just Work without manually starting databases. | MEDIUM | Currently: `docker_backends.py` starts containers. Desired: Docker Compose services auto-managed, not individually scripted. |
| **Error path testing** | Bad URIs, bad credentials, bad driver paths, bad entrypoint symbols must produce meaningful errors — not crashes, not silent failures. Users expect the suite to catch regressions that degrade error messages. | LOW | Existing: `test_negative.py` (7 tests) covers PROP-02, VAL-03, VAL-04, PROP-05, duplicate names. Per-driver negative tests (bad URI, wrong password) in each module. |
| **Clean teardown** | Every test drops its catalog in `finally` blocks. Docker containers are stopped on session teardown. No state pollution between runs. Users expect `pytest --count=10` to produce identical results. | LOW | Existing: `drop_catalog()` called in `finally:` in every test. Session-scoped fixtures with teardown. |
| **Structured pass/fail reporting** | pytest output shows pass/fail per test, per driver. Users scanning 35+ tests need to instantly see which driver regressed. | LOW | Existing: pytest's native output. JSON report via `pytest --json-report`. Marker-based test selection. |
| **Log capture on failure** | When a test fails, relevant StarRocks logs (FE log, BE log) are captured and attached to the test report. Users debugging a failure shouldn't need to ssh into containers or tail files manually. | LOW | Partially existing: `capture_on_failure` fixture in conftest.py tails FE/BE logs. Needs extension to capture container logs in Docker Compose mode. |

### Differentiators (Competitive Advantage)

Features that make this suite superior to ad-hoc testing or simpler integration suites.
Aligns with the Core Value: **verify before merge — catch regressions fast.**

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Cross-driver JOIN verification** | The killer feature. A single StarRocks query JOINs two completely different ADBC backends — e.g., SQLite `employees` JOIN PostgreSQL `departments` on `dept_id`. Proves the ADBC catalog layer correctly federates heterogeneous data sources. No other ADBC verification suite tests this. | MEDIUM | Existing: 4 cross-join tests across `test_cross_join.py` and `test_mysql.py`. SQLite↔PostgreSQL, two-SQLite, MySQL↔SQLite. Uses fully-qualified three-part names (`catalog.schema.table`). |
| **TPC-H query corpus** | Industry-standard benchmark schema and queries pre-loaded into every backend database. Verifies the ADBC connector handles complex SQL: aggregations, JOINs, subqueries, GROUP BY, ORDER BY, window functions. Queries stored as standalone SQL files — versionable, iterable, editable without rebuilding images. | HIGH | The `remote_table_verification` reference loads TPC-H via `init-pg.sql` and `init-sr.sql`. This project extends TPC-H to all backends (MySQL, FlightSQL, DuckDB, SQLite) and externalizes queries to `queries/` directory. |
| **Externalized SQL queries** | SQL query files live in a `queries/` directory outside Docker Compose. Editors can verify, format, and version-control queries independently of test infrastructure. The test runner maps query files to catalogs via environment variables or per-driver config. No rebuild needed to change a test query. | MEDIUM | Requires: query file naming convention, catalog mapping config, parameterized execution. The test runner opens `queries/tpch/01.sql`, substitutes catalog/database names, executes, asserts. |
| **Docker Compose self-containment** | `docker compose up` brings up the entire environment: StarRocks container (from shipped .deb) + PostgreSQL + MySQL + FlightSQL/SQLite + DuckDB on a Docker network. No locally running StarRocks, no manual port management. One command to up, one to down. Service discovery via Docker DNS. | HIGH | Pattern proven in `remote_table_verification`'s `docker-compose.yml`. Services: `sr-main`, `pg-tpch`, `mysql-tpch`, `flightsql`, `duckdb`. Docker bridge network. Health checks coordinate startup order. |
| **Ship→verify→retest loop** | The inner dev loop that makes the suite actually useful for StarRocks developers: (1) build .deb in StarRocks repo, (2) copy to `docker/`, (3) `docker compose up -d --build`, (4) `pytest`, (5) fix, repeat. No manual startup, no `STARROCKS_HOME` env var. | MEDIUM | `remote_table_verification` has this: build.sh → dpkg → copy .deb → `docker compose up --build` → pytest. This project adds a CLI runner (`run-verify.sh`) that orchestrates the full cycle. |
| **TLS verification per-driver** | Certificate-authenticated connections tested for both FlightSQL (gRPC TLS with self-signed certs and `adbc.flight.sql.client_option.tls_root_certs` pass-through) and PostgreSQL (`sslmode=verify-ca` with extracted CA certs). Proves the ADBC driver correctly configures TLS and validates certificates. | MEDIUM | Existing: `test_flightsql_tls_lifecycle` (extracts root-ca.pem via `docker cp`), `test_postgres_tls_verified` (enables SSL in container, extracts server.crt). |
| **adbc.* pass-through verification** | Systematically proves that StarRocks forwards `adbc.*` prefixed properties to the ADBC driver verbatim (PROP-05) — rather than rejecting them as unknown catalog properties. Tests use driver-specific options (`adbc.duckdb.threads`, `adbc.flight.sql.rpc.call_header.*`, `adbc.postgresql.quirks.*`) and verify the error originates from the driver, not StarRocks validation. | LOW | Existing: 5 pass-through tests across all driver modules and `test_negative.py`. The test pattern: create catalog with `adbc.*` key → if error, assert error message is driver-specific, not "Unknown catalog property". |
| **Comprehensive negative test suite** | Systematic coverage of every validation rule: mutual exclusion of `driver_url`/`driver_name` (PROP-02), missing both, file not found (VAL-03), bad entrypoint symbol (VAL-03), unknown top-level properties naming the key (VAL-04), duplicate catalog names. 7 tests that catch validation regression bugs before they ship. | LOW | Existing: `test_negative.py` with 7 tests. Each test asserts specific error message content (key name, path, mutual exclusion language). |
| **Auto-detected driver registry** | Reads installed ADBC driver paths from `~/.config/adbc/drivers/*.toml` manifests. The suite adapts to whatever drivers `dbc install` has installed — no hardcoded paths. Supports `linux_amd64` and `linux_arm64` architectures via platform detection. | LOW | Existing: `driver_registry.py` parses TOML files with `tomllib`, maps `platform.machine()` to dbc arch keys. |
| **Structured failure diagnostics** | On test failure, automatically captures: FE log tail (last 50 lines), BE log tail (last 50 lines), and (in Docker Compose mode) container logs from backend services. Attached to pytest's `user_properties` for JSON report consumers. | MEDIUM | Partially existing: `capture_on_failure` attaches FE/BE log tails. Docker Compose mode needs `docker compose logs` capture per-failing-test. |
| **Fast iteration path** | Run only the tests relevant to a change: `pytest tests/ -k flightsql` after FlightSQL driver changes, or `pytest tests/ -k cross_join` after federation changes. Combined with Docker Compose's container reuse (`up -d` without `--build` when DEB hasn't changed), the cycle is seconds not minutes. | LOW | Leverages existing pytest markers (`@pytest.mark.sqlite`, `@pytest.mark.flightsql`, `@pytest.mark.cross_join`, `@pytest.mark.negative`, `@pytest.mark.tls`). |
| **CLI runner** | Single command orchestrates the full cycle: `./run-verify.sh /path/to/starrocks-fe.deb /path/to/starrocks-be.deb`. Copies .deb files, builds containers, waits for health checks, runs full test suite, produces report, optionally tears down. | MEDIUM | The `remote_table_verification`'s CLAUDE.md documents the rebuild steps manually. A CLI runner formalizes and error-checks each step. Must handle: docker compose up, health wait, test run, report generation, cleanup on failure. |

---

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create complexity without value for this domain.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Performance benchmarking** | "Let's also measure query latency while we're running tests." | Wall-clock timing is noisy in Docker, varies by host load, and distracts from the core question: "does it work?" Surface-level performance numbers create false confidence. Performance is a separate concern requiring controlled environments, statistical analysis, and dedicated tooling. | Run `EXPLAIN ANALYZE` queries ad-hoc when investigating specific performance questions. Separate benchmarking suite if needed later. |
| **In-Docker pytest execution** | "Run pytest inside the StarRocks container so everything is self-contained." | Adds complexity: volume mounts for test files, image rebuild for every test change, Docker-in-Docker concerns, slower iteration. The `remote_table_verification` project runs pytest from the host for good reason — it's faster and simpler. | Host runs pytest against Docker Compose's published MySQL port. Test files live on host (versionable, editable without rebuild). This matches the proven rtv pattern. |
| **Real data volume testing** | "Load 100M TPC-H rows to test at scale." | A correctness suite doesn't need production-scale data. Small seed data (3-5 rows per table) runs in seconds and catches the same connector bugs. Large data adds minutes to test runtime, requires more disk space, and disproportionately tests StarRocks' scan performance (not ADBC correctness). | Seed tables with representative but tiny datasets (3-5 rows covering edge cases). Scale testing belongs in a separate performance suite. |
| **OAuth / Kerberos authentication** | "Support enterprise auth mechanisms for completeness." | Those authentication mechanisms require external infrastructure (KDC, OAuth provider) that breaks the self-contained Docker Compose model. The complexity-to-value ratio is poor for a connector verification suite — the ADBC auth layer is username/password and TLS, which covers the integration path. | Username/password auth is tested per-driver. TLS certificate auth is tested for FlightSQL and PostgreSQL. OAuth/Kerberos is an enterprise integration concern, not a connector verification concern. |
| **Multi-architecture builds (ARM/AArch64)** | "Support Apple Silicon and ARM servers." | The StarRocks .deb packages are amd64 only. ARM support would require building StarRocks from source for ARM, which is a separate build system concern. The verification suite tests what ships — and what ships is x86_64. | x86_64 only. The `driver_registry.py` already handles arch detection for future ARM support, but the Docker Compose environment is amd64. |
| **CI/CD pipeline integration (v1)** | "Run this in GitHub Actions on every PR." | Premature CI integration forces decisions about artifact caching, DEB storage, Docker layer caching, and runner configuration that are better deferred until the local suite is stable and proven. CI is a consumer of the suite, not a feature of the suite. | Local-first design. The CLI runner (`run-verify.sh`) is designed to be callable from CI later. CI configuration lives in a separate `.github/workflows/` file that invokes the CLI runner. |
| **Interactive test debugging mode** | "Drop into pdb on test failure for debugging." | pytest's native `--pdb` flag already provides this. Adding custom debugging infrastructure duplicates pytest functionality and adds maintenance burden. | Developers use `pytest --pdb` or `pytest --trace` as needed. No custom debugging mode needed. |
| **Real-time test progress dashboard** | "A web UI showing test progress in real time." | A verification suite is a CLI tool for developers and CI. A web dashboard is a separate project with a different architecture (websocket server, UI framework, state management). The complexity far exceeds the value. | pytest's terminal output shows progress in real time. JSON reports provide structured results for downstream consumers. |
| **Rollback/state checkpointing** | "Save and restore the entire Docker state between test phases." | Docker Compose already provides clean state management via `docker compose down` and `up`. Adding snapshot/restore adds Docker volume management complexity for no gain — the test data is tiny and re-seeds in seconds. | Start fresh each run. Docker Compose down → up provides clean state. Test data seeding is idempotent and fast. |

---

## Feature Dependencies

```
Docker Compose self-containment
    ├──requires──> Per-driver test modules (catalogs need backends)
    ├──requires──> Backend database provisioning (containers must exist)
    └──enables───> Ship→verify→retest loop (needs containerized StarRocks)

TPC-H query corpus
    ├──requires──> Backend database provisioning (schemas + data in containers)
    ├──requires──> Externalized SQL queries (queries need to live somewhere)
    └──enhances──> Data round-trip verification (richer queries, not just SELECT *)

Externalized SQL queries
    ├──enables───> TPC-H query corpus (queries as files)
    └──enhances──> Fast iteration path (edit query file, re-run, no rebuild)

Cross-driver JOIN verification
    ├──requires──> Per-driver test modules (needs two catalogs to exist)
    └──enhances──> Data round-trip verification (federation, not just per-backend)

CLI runner
    ├──requires──> Docker Compose self-containment (needs `docker compose` commands)
    └──enables───> Ship→verify→retest loop (orchestrates the cycle)

Ship→verify→retest loop
    ├──requires──> CLI runner (needs orchestration)
    └──enhances──> Fast iteration path (the loop IS the fast path)

Log capture on failure
    ├──enhances──> Structured failure diagnostics (log capture feeds diagnostics)
    └──requires──> Docker Compose self-containment (needs `docker compose logs`)

TLS verification
    ├──requires──> Backend database provisioning (containers with TLS configured)
    └──enhances──> Error path testing (TLS errors are a class of error paths)

adbc.* pass-through verification
    └──enhances──> Comprehensive negative test suite (PROP-05 validation)

Structured failure diagnostics
    ├──requires──> Log capture on failure (needs log content)
    └──enhances──> Structured pass/fail reporting (attaches diagnostics to reports)
```

### Dependency Notes

- **Docker Compose self-containment is the foundation.** Everything else depends on having backend databases running in a predictable, discoverable way. Phase 1 must deliver this.
- **Cross-driver JOIN verification requires at least two per-driver test modules working.** You can't JOIN what you can't query individually. This is a Phase 2 feature.
- **TPC-H query corpus requires all backends to have TPC-H schema loaded.** This means Docker Compose services must execute init SQL on startup. This is a Phase 2 feature.
- **CLI runner and ship→verify→retest loop are the payoff.** They make the suite usable in the inner dev loop. These are Phase 3 features — they depend on the foundation being solid.
- **adbc.* pass-through is already implemented** but its value is enhanced when combined with the TPC-H corpus (proving pass-through options work with complex queries).

---

## MVP Definition

### Launch With — Phase 1: Foundation

Minimum viable verification suite — proves the Docker Compose pattern works end-to-end.

- [x] **Per-driver test modules** — Already exists (35 tests across 5 driver modules + cross-join + negative)
- [x] **Catalog lifecycle testing** — Already exists (every test does CREATE → use → DROP)
- [x] **Data round-trip verification** — Already exists (3-row test_data per driver)
- [x] **Error path testing** — Already exists (test_negative.py, per-driver negative tests)
- [x] **Clean teardown** — Already exists (finally blocks, session teardown)
- [x] **Structured pass/fail reporting** — Already exists (pytest + JSON reports)
- [x] **Log capture on failure** — Already exists (capture_on_failure fixture)
- [ ] **Docker Compose self-containment** — **THE v1 deliverable.** Adapt conftest.py from host-port Docker calls to Docker Compose service names on a bridge network. StarRocks from DEB in Dockerfile. All backends as named services.
- [ ] **Backend database provisioning (Compose mode)** — Replace `docker_backends.py` subprocess calls with Docker Compose services, health checks, init SQL.

### Add After Validation — Phase 2: Depth

Features that make the suite comprehensive — add once the Docker Compose foundation works.

- [x] **Cross-driver JOIN verification** — Already exists (4 tests), but will use Docker service names instead of `127.0.0.1` in Compose mode
- [x] **adbc.* pass-through verification** — Already exists (5 tests across all drivers)
- [x] **Comprehensive negative test suite** — Already exists (7 tests in test_negative.py)
- [x] **Auto-detected driver registry** — Already exists (driver_registry.py reads TOML manifests)
- [ ] **TPC-H query corpus** — Load TPC-H schema + seed data into ALL backends (PostgreSQL, MySQL, FlightSQL, DuckDB, SQLite). Write TPC-H query SQL files in `queries/`. Run them through StarRocks ADBC catalogs and verify results.
- [ ] **Externalized SQL queries** — Extract queries from test files into standalone `queries/` directory. Test runner reads query files, substitutes catalog/database names, executes, asserts.
- [ ] **TLS verification (all drivers)** — Already partially exists for FlightSQL and PostgreSQL. Extend to MySQL if the ADBC MySQL driver supports TLS options.

### Future Consideration — Phase 3: Developer Experience

Features that make the suite a joy to use daily. Defer until foundation + depth are solid.

- [ ] **CLI runner (`run-verify.sh`)** — Single command that accepts .deb paths, copies to `docker/`, builds containers, waits for health, runs tests, produces report. Error-handles every step.
- [ ] **Ship→verify→retest loop** — The CLI runner + fast iteration path combined into a documented workflow. Developers can go from code change to test results in under 2 minutes.
- [ ] **Fast iteration path** — Documented patterns for running subset tests (`-k` flags, marker selection). Optimize `docker compose up` with `--no-build` when DEB hasn't changed.
- [ ] **Structured failure diagnostics (extended)** — Capture `docker compose logs` from relevant backend services on test failure. Attach to JSON report.
- [ ] **Health check dashboard** — A simple `check-env.sh` script that verifies all Docker services are healthy, catalogs are creatable, and basic queries run. Fast pre-flight before full test suite.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Docker Compose self-containment | HIGH — makes the suite usable without manual setup | HIGH — Dockerfile, docker-compose.yml, conftest rewrite | **P1** |
| Backend database provisioning (Compose) | HIGH — replaces manual docker run calls | MEDIUM — services in compose file, init SQL | **P1** |
| TPC-H query corpus | HIGH — industry-standard queries prove connector correctness | HIGH — schema portability across 5 backends, query file authoring | **P2** |
| Externalized SQL queries | MEDIUM — enables query versioning and iteration | MEDIUM — query file format, catalog mapping, substitution engine | **P2** |
| Cross-driver JOIN verification | HIGH — proves federation core value | LOW — already implemented, adapt to Compose names | **P2** |
| CLI runner | HIGH — makes the suite one-command runnable | MEDIUM — bash script with error handling, health polling | **P3** |
| Ship→verify→retest loop | HIGH — the inner dev loop payoff | LOW — documented workflow, depends on CLI runner | **P3** |
| Fast iteration path | MEDIUM — saves developer time | LOW — documented pytest invocations, compose optimization | **P3** |
| Structured failure diagnostics (extended) | MEDIUM — better debugging | MEDIUM — compose log capture, json report integration | **P3** |
| Per-driver test modules | HIGH — already exists | N/A — already implemented | **Done** |
| Catalog lifecycle testing | HIGH — already exists | N/A — already implemented | **Done** |
| Data round-trip verification | HIGH — already exists | N/A — already implemented | **Done** |
| Error path testing | HIGH — already exists | N/A — already implemented | **Done** |
| Clean teardown | MEDIUM — already exists | N/A — already implemented | **Done** |
| Structured pass/fail reporting | MEDIUM — already exists | N/A — already implemented | **Done** |
| Log capture on failure | MEDIUM — already exists | N/A — already implemented | **Done** |
| TLS verification | MEDIUM — already exists | N/A — already implemented | **Done** |
| adbc.* pass-through verification | MEDIUM — already exists | N/A — already implemented | **Done** |
| Comprehensive negative test suite | MEDIUM — already exists | N/A — already implemented | **Done** |
| Auto-detected driver registry | MEDIUM — already exists | N/A — already implemented | **Done** |

**Priority key:**
- **P1**: Must have for milestone completion — Docker Compose self-containment is the whole point of this milestone
- **P2**: Should have, adds significant value — TPC-H corpus and externalized queries are the depth that justifies the Docker Compose investment
- **P3**: Nice to have, developer experience polish — CLI runner and fast iteration path make daily use pleasant
- **Done**: Already implemented in the existing 35-test suite; needs adaptation (not new construction) for Docker Compose mode

---

## Competitor Feature Analysis

The reference competitor is the `remote_table_verification` project at `/home/mete/coding/remote_table_verification/`.
It uses the same Docker Compose pattern (rtv-main from DEB, rtv-sr1/2 for FlightSQL, rtv-pg1/2 for PostgreSQL) and
runs pytest from the host. This project extends that pattern.

| Feature | remote_table_verification | adbc_verification (target) | Our Approach |
|---------|---------------------------|---------------------------|--------------|
| Backend databases | PostgreSQL (2 instances), FlightSQL/StarRocks (2 instances) | PostgreSQL, MySQL, FlightSQL/SQLite, DuckDB, SQLite | **Broader coverage** — MySQL and DuckDB are new; SQLite via file is new. 5 backends vs 2. |
| TPC-H data | Loaded via init SQL files in PostgreSQL and StarRocks backends | Loaded in ALL backends (including MySQL, FlightSQL, DuckDB, SQLite) | **Universal TPC-H** — every backend gets TPC-H, not just PostgreSQL. |
| Query corpus | Embedded in test files (remote_table TVF queries) | Externalized SQL files in `queries/` directory, runnable against any catalog | **Externalized + parameterized** — queries are standalone artifacts, not embedded in test code. |
| Cross-driver JOINs | Not tested | 4 cross-join tests (SQLite↔PostgreSQL, two-SQLite, MySQL↔SQLite) | **Federation verification** — this is the distinguishing feature. |
| Negative tests | Not comprehensive | 7 systematic negative tests covering ALL validation rules | **Validation completeness** — every PROP/VAL rule has a corresponding test. |
| Ship→verify loop | Documented in CLAUDE.md as manual steps | CLI runner (`run-verify.sh`) automates the full cycle | **Automated loop** — single command, not manual copy-paste steps. |
| Log capture | Not present | FE/BE log tail on failure + container logs (planned) | **Diagnostics on failure** — developers get logs automatically. |
| adbc.* pass-through | Not tested | 5 pass-through tests proving PROP-05 | **Property forwarding validation** — catches StarRocks validation bugs. |
| Driver registry | Hardcoded driver paths in conftest.py | Auto-detected from `~/.config/adbc/drivers/*.toml` | **Portable** — adapts to whatever drivers `dbc install` provides. |
| TLS | Not tested | FlightSQL TLS (self-signed certs) + PostgreSQL TLS (verify-ca) | **Security validation** — TLS is tested end-to-end. |

---

## Sources

- **Existing test suite** — `tests/test_sqlite.py`, `tests/test_duckdb.py`, `tests/test_mysql.py`, `tests/test_postgres.py`, `tests/test_flightsql.py`, `tests/test_cross_join.py`, `tests/test_negative.py` — the 35-test baseline
- **Reference implementation** — `/home/mete/coding/remote_table_verification/` — Docker Compose pattern (`docker-compose.yml`, `Dockerfile`, `entrypoint.sh`), TPC-H init SQL (`init-pg.sql`, `init-sr.sql`), conftest with Docker network hostnames
- **PROJECT.md** — Core Value ("verify before merge"), active requirements DC-01 through DC-10, out-of-scope items, constraints
- **StarRocks ADBC catalog API** — PROP-02 (driver_url vs driver_name mutual exclusion), PROP-04 (top-level key validation), PROP-05 (adbc.* pass-through), VAL-03 (file not found, entrypoint missing), VAL-04 (unknown key naming) — all validated by existing test suite
- **CLAUDE.md** — Test patterns, fixture structure, project layout, prerequisites

---

*Feature research for: StarRocks ADBC Built-In Verification Suite*
*Researched: 2026-04-27*
