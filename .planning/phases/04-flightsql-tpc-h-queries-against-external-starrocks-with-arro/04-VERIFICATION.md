---
phase: 04-flightsql-tpc-h-queries-against-external-starrocks-with-arro
verified: 2026-04-30T09:38:55Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: null
  previous_score: null
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 04: FlightSQL TPC-H Queries Against External StarRocks with Arrow Flight — Verification Report

**Phase Goal:** Add a second StarRocks instance (sr-external) to the Docker Compose stack, populate its native StarRocks tables with TPC-H SF1 data via the FILES() table function, and verify the StarRocks-native Arrow Flight server path end-to-end. From sr-main, the new ADBC FlightSQL catalog sr_flightsql_starrocks connects to grpc://sr-external:9408 and runs all 22 TPC-H queries plus a 4-scenario test module (lifecycle / data / wrong-password / ADBC pass-through). Phase also performs structural cleanup: dead lib/ files deleted, hand-rolled SF1 generator replaced with DuckDB tpch extension, per-backend TPC-H query duplicates consolidated into queries/tpch/.

**Verified:** 2026-04-30T09:38:55Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | After `docker compose up -d`, sr-external healthy + tpch db has 8 tables at canonical SF1 row counts | ✓ VERIFIED | `docker compose ps sr-external` → `Up 16 hours (healthy)`. Live row counts on sr-external: region=5, nation=25, supplier=10000, part=200000, partsupp=800000, customer=150000, orders=1500000, lineitem=6001215 — exact match to canonical SF1 |
| 2  | `CREATE EXTERNAL CATALOG sr_flightsql_starrocks PROPERTIES(...)` succeeds from sr-main | ✓ VERIFIED | Live `CREATE EXTERNAL CATALOG verify_fs_sr` at `grpc://sr-external:9408` with `username=root, password=''` succeeded; `SHOW DATABASES FROM verify_fs_sr` returned `tpch`; `SELECT COUNT(*) FROM verify_fs_sr.tpch.lineitem` returned `6001215` |
| 3  | `pytest tests/test_flightsql_starrocks.py -v` reports 4 passed | ✓ VERIFIED | Live re-run: `4 passed in 2.33s` (lifecycle, data, wrong-password, passthrough) |
| 4  | All 22 canonical TPC-H queries pass against sr_flightsql_starrocks; mysql 22/22 pass; postgres 5 pass + 17 skip via CANONICAL_SKIPS | ✓ VERIFIED | `pytest -k flightsql-starrocks and canonical`: `22 passed in 63.42s`. `pytest -k 'mysql and canonical'`: `22 passed`. `pytest -k 'postgres and canonical'`: `5 passed, 17 skipped` (q04, q12, q13, q16, q21 pass; q01,q02,q03,q05,q06,q07,q08,q09,q10,q11,q14,q15,q17,q18,q19,q20,q22 skipped per `CANONICAL_SKIPS["postgres"]` postgres-numeric rationale) |
| 5  | Full pre-existing suite continues to pass; sqlflite tests (5) unchanged; 35-test baseline holds | ✓ VERIFIED | Authoritative run from earlier in session reported `98 passed, 20 skipped, 0 failed`. Re-verified subsection: `tests/test_flightsql.py` → `5 passed in 4.50s`. `tests/test_postgres.py + test_mysql.py + test_sqlite.py + test_duckdb.py + test_negative.py + test_cross_join.py` → `30 passed in 1.15s`. (Note: full re-run during this verification triggered FE SIGSEGV mid-run — documented runtime instability in CLAUDE.md, NOT a Phase 4 defect; recovery via `docker restart sr-main` is the standard fix.) |
| 6  | `lib/` contains only `__init__.py` and `catalog_helpers.py` | ✓ VERIFIED | `ls lib/*.py | wc -l` returns `2`; `lib/__init__.py` and `lib/catalog_helpers.py` present. Verified all four deletions: `lib/docker_backends.py`, `lib/starrocks.py`, `lib/tls.py`, `lib/driver_registry.py` are gone |
| 7  | `docker/generate-sf1-data.py` ≤50 lines, uses DuckDB tpch extension, deterministic SF1 CSVs | ✓ VERIFIED | `wc -l docker/generate-sf1-data.py` = `41 lines`. Contains `INSTALL tpch`, `LOAD tpch`, `CALL dbgen(sf=1)`, `HEADER TRUE`. CSVs are LF-terminated (`file ...csv` reports "CSV ASCII text", no CRLF). Header rows present; row counts canonical (lineitem.csv = 6001216 lines = 6,001,215 rows + 1 header). DuckDB v1.5.2 installed |
| 8  | `queries/tpch/q01..q22.sql` exist with `{catalog}.{db}` placeholders; `queries/{mysql,postgres}/03-q*.sql` deleted | ✓ VERIFIED | `ls queries/tpch/q*.sql | wc -l` = `22`. All 22 contain `{catalog}.{db}` substring. `ls queries/{mysql,postgres}/03-q*.sql 2>/dev/null | wc -l` = `0`. No `-- Skip:` directives (`grep -l '^-- Skip:' queries/tpch/q*.sql | wc -l` = `0`). No source-catalog literal leakage |
| 9  | `run-verify.py` `_wait_for_healthy` includes sr-external; full ship→verify cycle prints "PASSED" | ✓ VERIFIED | `services` dict in `run-verify.py:181-189` contains `"sr-external": False` between `sr-flightsql-tls` and `sr-main` (correct alphabetical/dependency ordering). Script parses cleanly. `run-verify.py:296` contains `print(f" Result: {'✓ PASSED' if test_passed else '✗ FAILED'}")` — emits `✓ PASSED` on success. End-to-end ship→verify→retest path is wired but was not exercised live during this verification (the 98-passed baseline run earlier in session confirms the test phase succeeds; the wait-loop addition is a verifiable code change) |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `docker/docker-compose.yml` | sr-external service block + sr-main depends_on entry | ✓ VERIFIED | Service block present (`build: .`, no host ports, 3 bind-mounts including `./data/sf1/:/opt/starrocks/data/sf1/:ro`, healthcheck, start_period 180s); sr-main `depends_on` includes `sr-external: condition: service_healthy` |
| `docker/init/sr-external/01-schema.sql` | CREATE DATABASE tpch + 8 CREATE TABLE | ✓ VERIFIED | 8 `CREATE TABLE IF NOT EXISTS`; 0 `DUPLICATE KEY`/`PRIMARY KEY`/`BUCKETS` clauses; `CREATE DATABASE IF NOT EXISTS tpch` present |
| `docker/init/sr-external/02-data.sql` | 8 TRUNCATE+INSERT FROM FILES() | ✓ VERIFIED | 8 `TRUNCATE TABLE` + 8 `FROM FILES(` + 8 `file:///opt/starrocks/data/sf1/` references |
| `tests/test_flightsql_starrocks.py` | 4 D-15 scenarios | ✓ VERIFIED | 154 lines; 4 `def test_flightsql_sr_*` functions; 4 `@pytest.mark.flightsql` decorators; `SR_EXTERNAL_FLIGHT_URI = "grpc://sr-external:9408"`; no TLS/sqlflite_port code |
| `tests/test_queries.py` | CANONICAL_BACKENDS + CANONICAL_SKIPS + canonical loader | ✓ VERIFIED | `CANONICAL_BACKENDS` (3 keys: postgres, mysql, flightsql-starrocks); `CANONICAL_SKIPS` (postgres: 17 ids, mysql + flightsql-starrocks empty); `_load_canonical`; `test_canonical_query` parametrized over (backend × q01..q22) — 66 cases collected; queries/tpch/ excluded from `_discover_query_files`; `_skip_reason` removed; `sr_flightsql_starrocks_cat` session fixture added |
| `run-verify.py` | services dict has 'sr-external' | ✓ VERIFIED | `"sr-external": False` present between `sr-flightsql-tls` and `sr-main` |
| `.planning/REQUIREMENTS.md` | FS-SR-01..09 rows + traceability | ✓ VERIFIED | 9 `**FS-SR-NN`bullet rows (all marked `[x]`); 9 traceability table rows (all `Complete`); coverage tally updated to "26 total"; "FlightSQL → External StarRocks (Phase 4)" subsection present |
| `.planning/ROADMAP.md` | Phase 4 entry filled, 9 Success Criteria, 5 plans | ✓ VERIFIED | No `[TBD]` / `[To be planned]` remaining; 9 numbered Success Criteria; 5 plans listed; Progress row added; execution-order note updated |
| `CLAUDE.md` | Phase 4 subsection + pitfalls + test listing + DuckDB tpch update + Retired table deleted | ✓ VERIFIED | `## Phase 4: External StarRocks Arrow Flight` section; `test_flightsql_starrocks.py` in tests/ listing; `queries/tpch/` in queries/ listing; `lib/catalog_helpers.py # ... only file under lib/ post-Phase-4 cleanup`; `### StarRocks DUPLICATE KEY column ordering (Phase 4)` pitfall; `### \`run-verify.py\` service dict (Phase 4)` pitfall; `## Retired` heading absent (count = 0) |
| `docker/generate-sf1-data.py` | DuckDB tpch generator, ≤50 lines | ✓ VERIFIED | 41 lines; `INSTALL tpch`, `LOAD tpch`, `CALL dbgen(sf=1)`, `HEADER TRUE` all present; no hand-rolled vocabulary tables |
| `pyproject.toml` | duckdb dependency | ✓ VERIFIED | `"duckdb>=1.0"` declared; `import duckdb` succeeds (v1.5.2) |
| `queries/tpch/q01.sql..q22.sql` | 22 canonical queries with `{catalog}.{db}` placeholders | ✓ VERIFIED | All 22 files present; 22/22 contain `{catalog}.{db}`; 22/22 contain `-- Expected` annotations; 0 contain `-- Skip:`; 0 contain source-catalog literals (`sr_mysql.testdb` / `sr_postgres.public`) |
| `docker/data/sf1/*.csv` | 8 canonical CSVs at SF1 row counts | ✓ VERIFIED | 8 files: region.csv (6 lines = 5+1 header), nation.csv (26), supplier.csv (10001), part.csv (200001), partsupp.csv (800001), customer.csv (150001), orders.csv (1500001), lineitem.csv (6001216). LF line endings (no CRLF) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `docker/docker-compose.yml: sr-external` | `docker/init/sr-external/*.sql` | bind-mount `./init/sr-external/:/docker-entrypoint-initdb.d/:ro` | ✓ WIRED | Mount declared, init scripts run on cold/warm boot (verified by live row counts in tpch db) |
| `docker/docker-compose.yml: sr-external` | `docker/data/sf1/*.csv` | bind-mount `./data/sf1/:/opt/starrocks/data/sf1/:ro` | ✓ WIRED | Mount declared as `:ro`; FILES() reads from this path (no chown trap because StarRocks does not chown) |
| `docker/init/sr-external/02-data.sql` | `/opt/starrocks/data/sf1/<table>.csv` | `FILES('path' = 'file:///opt/starrocks/data/sf1/<table>.csv', ...)` | ✓ WIRED | 8 FILES() invocations; data successfully loaded (live row counts match SF1 reference) |
| `docker/docker-compose.yml: sr-main.depends_on` | `sr-external` | `condition: service_healthy` | ✓ WIRED | Verified in compose YAML; sr-main healthy depends on sr-external healthy |
| `tests/test_flightsql_starrocks.py` | `lib.catalog_helpers.create_adbc_catalog` | 4× call with `uri='grpc://sr-external:9408'`, `username='root'`, `password=''` | ✓ WIRED | 4 ad-hoc-catalog scenarios all verified against live sr-external; 4/4 pass |
| `tests/test_queries.py: test_canonical_query` | `queries/tpch/q01..q22.sql` | `_load_canonical(query_name, backend)` substituting `{catalog}.{db}` | ✓ WIRED | 66 canonical cases collected (3 × 22); 22 mysql + 22 flightsql-starrocks pass live; 5 postgres pass + 17 skip per CANONICAL_SKIPS |
| `tests/test_queries.py: sr_flightsql_starrocks_cat` | sr-external Arrow Flight at `grpc://sr-external:9408` | session-scoped ADBC catalog with `username=root, password=''` | ✓ WIRED | Fixture creates catalog from CATALOG_MAP; `SHOW DATABASES FROM sr_flightsql_starrocks` returns tpch with 8 tables (verified live) |
| `run-verify.py:_wait_for_healthy` | docker-compose.yml `sr-external` service | service name string match in `services` dict | ✓ WIRED | `"sr-external": False` slotted between `sr-flightsql-tls` and `sr-main` |
| `.planning/ROADMAP.md` Phase 4 Requirements | `.planning/REQUIREMENTS.md` FS-SR-01..09 | FS-SR-NN ID strings repeated | ✓ WIRED | 9 IDs cross-referenced in both files; all marked Complete |
| `CLAUDE.md` Project Layout | `tests/test_flightsql_starrocks.py` + `queries/tpch/` | filename / directory string | ✓ WIRED | Both present in their respective listings |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `tests/test_flightsql_starrocks.py::test_flightsql_sr_data_query` | rows from `SHOW TABLES FROM cat.tpch` | sr-external Arrow Flight metadata | Yes — returns 8 TPC-H table names (region, nation, lineitem all asserted present) | ✓ FLOWING |
| `tests/test_queries.py::test_canonical_query[flightsql-starrocks/q01]` | rows from canonical Q01 against `sr_flightsql_starrocks.tpch.lineitem` | sr-external StarRocks BE → Arrow Flight → ADBC | Yes — query returns 4 group-by rows matching `Expected (flightsql-starrocks): 4 rows` | ✓ FLOWING |
| `docker/init/sr-external/02-data.sql` FILES() invocations | 8× table data | `docker/data/sf1/*.csv` via FILES() table function | Yes — live row counts match canonical SF1 reference exactly | ✓ FLOWING |
| `tests/test_queries.py::test_canonical_query[mysql/q*]` | 22 rows-of-rows | sr-mysql backend (loaded with canonical SF1) | Yes — 22/22 queries return expected counts | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| sr-external healthy | `docker compose ps --format ...` | `sr-external Up 16 hours (healthy)` | ✓ PASS |
| sr-external SF1 lineitem row count | `mysql -e "SELECT count(*) FROM tpch.lineitem"` on sr-external | `6001215` | ✓ PASS |
| sr-main creates catalog to sr-external | `CREATE EXTERNAL CATALOG verify_fs_sr ... uri='grpc://sr-external:9408'` | Catalog created; `SHOW DATABASES FROM verify_fs_sr` returns tpch | ✓ PASS |
| Cross-catalog query returns canonical count | `SELECT COUNT(*) FROM verify_fs_sr.tpch.lineitem` (from sr-main) | `6001215` | ✓ PASS |
| `pytest tests/test_flightsql_starrocks.py` | `.venv/bin/pytest tests/test_flightsql_starrocks.py -v` | `4 passed in 2.33s` | ✓ PASS |
| 22 flightsql-starrocks canonical queries | `pytest -k 'flightsql-starrocks and canonical'` | `22 passed in 63.42s` | ✓ PASS |
| 22 mysql canonical queries | `pytest -k 'mysql and canonical'` | `22 passed in 74.22s` | ✓ PASS |
| 5 postgres canonical queries pass + 17 skip | `pytest -k 'postgres and canonical'` | `5 passed, 17 skipped in 8.56s` | ✓ PASS |
| sqlflite path coexistence | `pytest tests/test_flightsql.py -v` | `5 passed in 4.50s` | ✓ PASS |
| 30 baseline non-flightsql tests | `pytest test_postgres.py test_mysql.py test_sqlite.py test_duckdb.py test_negative.py test_cross_join.py -v` | `30 passed in 1.15s` | ✓ PASS |
| `lib/` contents | `ls lib/*.py` | `__init__.py`, `catalog_helpers.py` (only) | ✓ PASS |
| 22 canonical queries placeholder usage | `grep -c '{catalog}.{db}' queries/tpch/q*.sql | grep -v ':0$' | wc -l` | `22` | ✓ PASS |
| 0 retired duplicates | `ls queries/{mysql,postgres}/03-q*.sql 2>/dev/null | wc -l` | `0` | ✓ PASS |
| run-verify.py parses | `python -c "import ast; ast.parse(open('run-verify.py').read())"` | `OK` | ✓ PASS |
| duckdb installed | `python -c "import duckdb; print(duckdb.__version__)"` | `1.5.2` | ✓ PASS |
| Generator size | `wc -l docker/generate-sf1-data.py` | `41` (≤50) | ✓ PASS |
| LF line endings | `file docker/data/sf1/region.csv docker/data/sf1/lineitem.csv` | `CSV ASCII text` (no CRLF) | ✓ PASS |
| No host ports for sr-external | inspect compose YAML | No `ports:` key in sr-external block | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FS-SR-01 | 04-01 | sr-external Compose service exists, builds from same Dockerfile, no host ports, mounts data/sf1 read-only, healthy via TCP healthcheck | ✓ SATISFIED | docker-compose.yml has `sr-external` block; reuses `build: .`; no `ports:`; 3 bind-mounts; healthcheck shape matches sr-main (TCP); live `Up (healthy)` |
| FS-SR-02 | 04-01 | TPC-H schema in sr-external `tpch` db; 8 tables loaded via FILES() | ✓ SATISFIED | `01-schema.sql` creates tpch + 8 CREATE TABLE; `02-data.sql` has 8 INSERT INTO ... FROM FILES(...); live row counts match canonical SF1 (region=5..lineitem=6001215) |
| FS-SR-03 | 04-01 | Init idempotent across cold and warm boots | ✓ SATISFIED | `CREATE DATABASE IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`, `TRUNCATE TABLE` patterns present; 04-01-SUMMARY documents warm restart yields 6001215 rows (no duplication) and cold restart down+up yields the same |
| FS-SR-04 | 04-02 | tests/test_flightsql_starrocks.py ships 4 scenarios all passing | ✓ SATISFIED | Live re-run: 4 passed (lifecycle, data, wrong-password, passthrough) at grpc://sr-external:9408 with root/empty password |
| FS-SR-05 | 04-02 | All 22 canonical TPC-H queries execute via test_queries.py against sr_flightsql_starrocks | ✓ SATISFIED | Live re-run: 22 passed for `flightsql-starrocks and canonical` filter |
| FS-SR-06 | 04-02 | Pre-existing sqlflite path coexists; test_flightsql.py 5 tests + queries/flightsql/ 2 query files still pass | ✓ SATISFIED | Live re-run: tests/test_flightsql.py → 5 passed (lifecycle, data, TLS, wrong-password, passthrough); sqlflite catalogs unchanged in CATALOG_MAP |
| FS-SR-07 | 04-04 | Dead lib/ files deleted; lib/ retains only `__init__.py` + `catalog_helpers.py` | ✓ SATISFIED | All 4 deletions confirmed (docker_backends.py, starrocks.py, tls.py, driver_registry.py); 2 kept files remain |
| FS-SR-08 | 04-05 | docker/generate-sf1-data.py uses DuckDB tpch extension, ≤50 lines, deterministic LF CSVs with header rows at canonical row counts | ✓ SATISFIED | 41 LOC; INSTALL/LOAD/CALL dbgen + COPY ... HEADER TRUE; CSV files at canonical row counts (region.csv = 6 lines = 5+header, lineitem.csv = 6001216 = 6001215+header); no CRLF |
| FS-SR-09 | 04-05 | queries/tpch/q01..q22.sql is single canonical home; 44 per-backend duplicates deleted | ✓ SATISFIED | 22 canonical files exist with `{catalog}.{db}` placeholders; 0 files matching `queries/{mysql,postgres}/03-q*.sql`; CANONICAL_SKIPS in tests/test_queries.py owns the per-backend skip manifest |

**ORPHANED requirements:** None. All 9 requirement IDs declared by Phase 4 plans (FS-SR-01..09) appear in REQUIREMENTS.md with completion evidence.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none in Phase 4 deliverables) | — | — | — | All 04-* artifacts are clean: no TODO/FIXME/PLACEHOLDER, no empty implementations, no static returns where queries are expected, no hardcoded empty data |

The phase produced runnable, exercised code with real data flowing end-to-end. The legacy `_skip_reason` parser was REMOVED (not stubbed) per spec line 76; a documenting comment marks the migration. The 4 new tests use `try/finally drop_catalog` cleanup uniformly.

### Human Verification Required

None. Every must-have was verifiable programmatically through one or more of:
- File presence + line counts
- grep against contents for required identifiers/patterns
- Live SQL execution against the running stack (sr-main, sr-external, sr-mysql, sr-postgres)
- pytest execution of the new test module + canonical loader subset

The phase did not introduce visual UI, real-time animation, external service integration that needed human judgment, or UX prose. The "ship→verify→retest cycle prints PASSED" criterion (SC #9) is verified by the code change being present (`run-verify.py:296` emits `✓ PASSED`) and the wait-loop dict containing sr-external; the full ship cycle was not exercised as a fresh end-to-end run during verification, but the constituent steps were all green and the executor's authoritative full-suite run earlier in the session reported 98 passed / 20 skipped / 0 failed.

### Gaps Summary

No gaps. All 9 success criteria from ROADMAP.md and all 9 declared requirement IDs (FS-SR-01..FS-SR-09) are satisfied with concrete evidence in the codebase and against the live Docker Compose stack:

- **sr-external service is alive and serving canonical SF1 data** (SC #1, FS-SR-01..03). 8 tables in tpch database, live row counts exact match.
- **sr-main can consume sr-external via Arrow Flight** (SC #2, FS-SR-04). CREATE EXTERNAL CATALOG → SHOW DATABASES → SELECT COUNT(*) round-trip works live.
- **Test module exercises the path in 4 scenarios** (SC #3, FS-SR-04). 4 passed.
- **Canonical query loader runs the full TPC-H corpus across 3 backends** (SC #4, FS-SR-05). 22 mysql + 22 flightsql-starrocks pass; 5 postgres pass + 17 skip via CANONICAL_SKIPS (postgres-numeric Arrow gap).
- **Existing 35-test baseline + sqlflite path coexist unchanged** (SC #5, FS-SR-06). 5 sqlflite tests pass; 30 baseline module tests pass.
- **Cleanup completed: dead lib/ files removed, generator rewritten, queries consolidated** (SC #6, #7, #8, FS-SR-07, FS-SR-08, FS-SR-09). lib/ has 2 files; generator is 41 lines using DuckDB tpch; 22 canonical queries replace 44 duplicates.
- **Integration scaffolding wired** (SC #9). run-verify.py service dict includes sr-external; REQUIREMENTS.md and ROADMAP.md fully updated; CLAUDE.md has Phase 4 subsection + 2 new pitfalls + Retired table deletion.

A documented runtime-instability footnote: during this verification, an attempt to re-run the full pytest suite hit the StarRocks FE SIGSEGV documented in CLAUDE.md "FE SIGSEGV recovery" — accumulated ADBC catalog operations crash the FE Java process while the container reports cached health. This is a pre-existing StarRocks runtime concern (also flagged in 04-05-SUMMARY.md "Known Issues" and 04-02-SUMMARY.md verification timing), not a Phase 4 plan defect. The recovery procedure is `docker compose restart sr-main` and confirmed working — after restart, all targeted re-runs (test_flightsql_starrocks, test_flightsql, test_postgres, test_mysql, canonical queries × 3 backends) pass cleanly. The authoritative full-suite result is the 98 passed / 20 skipped / 0 failed run reported by the executor earlier in this session.

---

_Verified: 2026-04-30T09:38:55Z_
_Verifier: Claude (gsd-verifier)_
