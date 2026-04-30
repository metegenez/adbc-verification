---
phase: 04
plan: 04-02
title: ADBC FlightSQL→StarRocks Test Module + Canonical TPC-H Loader
subsystem: testing
tags: [adbc, flightsql, arrow-flight, starrocks, tpc-h, pytest, canonical-loader]

# Dependency graph
requires:
  - phase: 04-01
    provides: sr-external Compose service (healthy, TPC-H SF1 loaded into native StarRocks tables)
  - phase: 04-05
    provides: queries/tpch/q01..q22.sql canonical TPC-H corpus with {catalog}.{db} placeholders + per-backend Expected annotations
provides:
  - tests/test_flightsql_starrocks.py — 4 D-15 scenarios for sr_flightsql_starrocks (lifecycle, data, wrong-password, passthrough)
  - tests/test_queries.py — canonical loader contract: CANONICAL_BACKENDS, CANONICAL_SKIPS, _load_canonical, per-backend Expected parser, sr_flightsql_starrocks_cat fixture, test_canonical_query × test_query_file split
  - 66 canonical (query × backend) cases collected end-to-end (3 backends × 22 queries)
affects: [phase-05-future-canonical-extensions, future-backend-additions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Canonical TPC-H loader: single source-of-truth in queries/tpch/, per-backend substitution via str.format(catalog=…, db=…) at test-collection time"
    - "Per-backend skip manifest in test code (CANONICAL_SKIPS), replacing legacy inline `-- Skip:` SQL directives"
    - "Per-backend Expected annotations: `-- Expected (<backend>): N rows` parsed by _expected_rows; falls back to shared `-- Expected: N rows`"
    - "Two parametrized test functions on the same SQL corpus: test_canonical_query (cross-product) + test_query_file (per-directory legacy), with queries/tpch/ excluded from per-directory glob"
    - "Ad-hoc-catalog test pattern (defensive pre-clean → try → finally drop) cloned across the 4 scenarios — mirrors tests/test_flightsql.py"

key-files:
  created:
    - "tests/test_flightsql_starrocks.py — 154 lines, 4 D-15 scenarios at grpc://sr-external:9408 (root, empty password)"
  modified:
    - "tests/test_queries.py — canonical loader: CANONICAL_BACKENDS (3), CANONICAL_SKIPS (postgres: 17, mysql: 0, flightsql-starrocks: 0), _load_canonical, per-backend _expected_rows, sr_flightsql_starrocks_cat fixture, test_canonical_query parametrized over (backend × q01..q22), tpch/ excluded from _discover_query_files, _skip_reason removed"

key-decisions:
  - "Canonical home is queries/tpch/ owned by 04-05; 04-02 consumes via substitution loader — no per-backend SQL clones"
  - "tests/test_queries.py runs two parametrized test functions on the same corpus root: test_canonical_query for the cross product, test_query_file for legacy per-directory files. queries/tpch/ is excluded from the per-directory glob so canonical queries never double-parametrize"
  - "Per-backend skip manifest (CANONICAL_SKIPS) lives in test code, not in SQL files. The legacy inline `-- Skip:` parser is REMOVED — postgres-numeric Arrow gap (17 query ids) is keyed by (backend, query_name) in CANONICAL_SKIPS"
  - "DuckDB :memory: and FlightSQL-sqlflite-with-join skips stay INLINE in test_query_file — those backends are per-directory legacy, not canonical-cross-product participants (per 04-CANONICAL-SPEC.md line 79)"
  - "test_flightsql_sr_data_query is metadata-only (SHOW TABLES). The SELECT path is covered by all 22 canonical TPC-H queries running against the same backend; duplicating it here would be redundant"
  - "sr_flightsql_starrocks_cat fixture lives in tests/test_queries.py (not conftest.py) — mirrors sr_flightsql_cat placement; promoting to conftest.py would create a fixture-graph collision with tests/test_flightsql_starrocks.py's ad-hoc catalogs"
  - "TLS scenario intentionally OMITTED from tests/test_flightsql_starrocks.py per D-14 (plaintext only for v1)"

patterns-established:
  - "Canonical loader pattern: cross-product parametrization over (query × backend) with per-backend skip manifest, per-backend row-count expectations, and template substitution at test-collection time"
  - "Two-parametrize-on-one-corpus pattern: test_canonical_query (cross product) + test_query_file (per-directory) sharing queries/ as the root, with the canonical home excluded from the per-directory glob"

requirements-completed: [FS-SR-04, FS-SR-05, FS-SR-06]

# Metrics
duration: ~32min
completed: 2026-04-30
---

# Phase 04 Plan 04-02: ADBC FlightSQL→StarRocks Test Module + Canonical TPC-H Loader Summary

**Wired the FlightSQL→sr-external Arrow Flight path into the test suite via a canonical (query × backend) cross-product loader plus a 4-scenario test module, taking the suite from 71 baseline tests to 98 passing tests with 17 postgres canonical skips honored via the new CANONICAL_SKIPS manifest.**

## Performance

- **Duration:** ~32 min (from plan start at 2026-04-30T08:40:46Z through verification approval at 2026-04-30T09:55Z)
- **Started:** 2026-04-30T08:40:46Z
- **T01 committed:** 2026-04-30T08:43:53Z (3afe0d3)
- **T02 committed:** 2026-04-30T08:49:00Z (a31959b)
- **T03 verification ran:** 2026-04-30T08:50–09:55Z (full 9-step verification including the 219.57s full-suite regression)
- **Tasks:** 2 implementation tasks committed atomically + 1 human-verify checkpoint (approved)
- **Files modified:** 1 created, 1 refactored (no docker/, lib/, conftest.py, run-verify.py, REQUIREMENTS.md, ROADMAP.md, or CLAUDE.md touches per plan scope)

### Verification timing (T03)

| Step | Filter | Wall-clock | Outcome |
|------|--------|-----------:|---------|
| 1 | `tests/test_flightsql_starrocks.py` | 1.06s | 4 passed |
| 2 | `-k flightsql-starrocks` (canonical) | 39.69s | 22 passed |
| 3 | `-k 'mysql and canonical'` | 84.65s | 22 passed |
| 4 | `-k 'postgres and canonical'` | 7.58s | 5 passed, 17 skipped |
| 5 | `tests/test_flightsql.py` (D-12) | 2.44s | 5 passed |
| 6 | `tests/ -q` (full suite) | 219.57s | 98 passed, 20 skipped, 1 xpassed |
| 7 | Q01 lineitem COUNT via sr_flightsql_starrocks | (subsec) | 6001215 (canonical SF1) |
| 8 | `--collect-only test_query_file[tpch/...` | (subsec) | 0 (canonical home properly excluded) |
| 9 | `--collect-only test_canonical_query` | (subsec) | 66 cases (3 × 22) |

**Combined cross-product time (steps 2+3+4):** ~131.92s for the 66 canonical (query × backend) cases.

## Accomplishments

- New module `tests/test_flightsql_starrocks.py` validates the StarRocks-native Arrow Flight path end-to-end across 4 scenarios (catalog lifecycle, SHOW TABLES metadata, wrong-password auth gate, ADBC pass-through forwarding). All pass against `grpc://sr-external:9408` with `username=root` / `password=""`.
- `tests/test_queries.py` ships the canonical loader contract from `04-CANONICAL-SPEC.md`: 3-key `CANONICAL_BACKENDS`, `CANONICAL_SKIPS` with the 17-id postgres-numeric skip set, `_load_canonical(query_name, backend)` substituting `{catalog}.{db}` per backend, per-backend `_expected_rows(sql, backend=…)` precedence (`-- Expected (<backend>): N rows` over shared `-- Expected: N rows`), and a new `sr_flightsql_starrocks_cat` session fixture.
- 66 canonical (query × backend) cases now collect — `test_canonical_query` parametrized as `canonical[<backend>/q<NN>]`. 22 mysql + 5 postgres + 22 flightsql-starrocks pass; 17 postgres are SKIPPED via the manifest (no inline SQL skip directives, no `pytest.raises` workarounds).
- D-12 sqlflite path coexistence preserved — `tests/test_flightsql.py` still 5 passed unchanged. The legacy per-directory mechanism (`tests/test_queries.py::test_query_file`) still works for `queries/sqlite/`, `queries/duckdb/`, `queries/flightsql/`, `queries/cross-join/`, and the 4 surviving non-canonical `queries/{mysql,postgres}/01-select.sql` + `02-join.sql` files.
- `_skip_reason` and inline `-- Skip:` parsing removed from `tests/test_queries.py` per spec line 76; documented with a migration comment so a future reader understands the absence.

## Task Commits

Each task was committed atomically before the human-verify checkpoint:

1. **T01: Add tests/test_flightsql_starrocks.py with 4 D-15 scenarios** — `3afe0d3` (test): 154 lines, 4 ad-hoc-catalog scenarios mirroring `tests/test_flightsql.py` minus TLS (D-14). Hard-coded `SR_EXTERNAL_FLIGHT_URI = "grpc://sr-external:9408"` (D-16); `username=root, password=""` (D-13). Defensive `drop_catalog` before each `try` block; `finally: drop_catalog` on every test. `test_flightsql_sr_data_query` is metadata-only (SHOW TABLES) — SELECT path delegated to canonical TPC-H corpus.
2. **T02: Refactor tests/test_queries.py with canonical TPC-H loader** — `a31959b` (test): +160 / -22 lines. Adds `CANONICAL_BACKENDS` (postgres/mysql/flightsql-starrocks), `CANONICAL_SKIPS` (postgres has the 17 ids; mysql + flightsql-starrocks empty), `_load_canonical`, per-backend `_expected_rows`, `sr_flightsql_starrocks_cat` session fixture (root, empty password), `CATALOG_MAP[sr_flightsql_starrocks] = (flightsql_driver_path, grpc://sr-external:9408)`, `test_canonical_query` parametrized over (backend × q01..q22) with `canonical[<backend>/q<NN>]` ids, `_discover_query_files` extended to skip `queries/tpch/`, `_skip_reason` removed.

**Plan metadata commit:** _added below in this commit_ (`docs(04-02): ...`).

_Note: This plan had no TDD tasks; both T01 and T02 are direct test additions/refactors._

## Files Created/Modified

- **Created:** `tests/test_flightsql_starrocks.py` (154 lines) — 4 D-15 scenarios for sr_flightsql_starrocks, ad-hoc catalogs per test, no fixtures beyond `sr_conn` and `flightsql_driver_path` (both pre-existing in `conftest.py`).
- **Modified:** `tests/test_queries.py` (160 added / 22 deleted, 320 → 458 LOC after refactor) — canonical loader added; `_skip_reason` removed; `_discover_query_files` updated to exclude `queries/tpch/`; one new session fixture `sr_flightsql_starrocks_cat`; one new test function `test_canonical_query` alongside the legacy `test_query_file`.

## Decisions Made

- **No deviation from `04-CANONICAL-SPEC.md`.** All 17 postgres skips trigger via `CANONICAL_SKIPS["postgres"]` — zero `pytest.raises` workarounds were needed. The spec's `(backend, query_name)` skip manifest works as intended.
- **TLS scenario omitted** from the new test module per D-14 (plaintext-only for v1).
- **`test_flightsql_sr_data_query` trimmed to SHOW TABLES only** — the SELECT path is covered by all 22 canonical queries running against the same backend, so duplicating it would be wasted runtime and redundant assertion surface.
- **`sr_flightsql_starrocks_cat` placement at `tests/test_queries.py` (not `conftest.py`).** Mirrors `sr_flightsql_cat` placement — promoting to `conftest.py` would create a fixture-graph collision with the ad-hoc catalogs in `tests/test_flightsql_starrocks.py` (warned against in `04-PATTERNS.md` and `04-RESEARCH.md` "Don't Hand-Roll").
- **DuckDB :memory: and FlightSQL-sqlflite-with-join skips stay inline** in `test_query_file` (NOT migrated into `CANONICAL_SKIPS`) — those backends are per-directory legacy, not canonical-cross-product participants. Spec line 79 endorses this exact placement.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria for T01 (10 grep/python checks) and T02 (~20 grep/pytest checks) passed on the first verification pass. The full-suite verification step (T03 step 6) showed 1 unexpected `xpassed` signal, but it was identified as pre-existing phase-3 hygiene unrelated to 04-02 (see "Issues Encountered" below).

## Issues Encountered

- **`tests/test_benchmark_cli.py::test_explain_analyze_parser_extracts_total_for_q01` reports XPASS in full-suite scope.** This is a phase-3 benchmark test with an `xfail` marker that no longer applies (the parser fix it expected to be missing has presumably landed). It is **out of scope** for 04-02 — the 04-02 plan touches only `tests/test_flightsql_starrocks.py` and `tests/test_queries.py`. Per the user's direction, this xpassed signal is acknowledged here and will be resolved separately as phase-3 hygiene (remove the stale `xfail` marker so the test is reported as a regular pass). Logged for follow-up; not a 04-02 deviation.

## User Setup Required

None — no external service configuration required. The plan uses fixtures that were already provided by `conftest.py` (Phase 1) and consumes the `sr-external` service stood up by 04-01 + the canonical query corpus owned by 04-05.

## Next Phase Readiness

- **Phase 4 closure**: with 04-02 complete, all 5 plans of phase 04 are done (04-01, 04-02, 04-03, 04-04, 04-05). The full FlightSQL→StarRocks story is end-to-end verifiable: `./run-verify.py docker/starrocks-fe_*.deb docker/starrocks-be_*.deb` will exercise the canonical 22-query corpus across 3 backends plus the 4 ad-hoc-catalog scenarios on every shipped DEB.
- **Pending follow-up (out of 04-02 scope):** The phase-3 xpassed test (`test_benchmark_cli.py::test_explain_analyze_parser_extracts_total_for_q01`) needs its stale `xfail` marker removed. Tracked separately by the user.
- **Future canonical-corpus extensions**: any new (query × backend) addition is a single SQL file under `queries/tpch/` plus an entry in `CANONICAL_BACKENDS` — the loader pattern absorbs the rest.

## Self-Check: PASSED

- tests/test_flightsql_starrocks.py — exists (committed in 3afe0d3)
- tests/test_queries.py — modified (committed in a31959b)
- 04-02-SUMMARY.md — exists at .planning/phases/04-…/04-02-SUMMARY.md
- Commit 3afe0d3 — present in git log (T01 atomic commit)
- Commit a31959b — present in git log (T02 atomic commit)
- ROADMAP.md — 04-02 plan checkbox flipped [x]; Phase 4 progress row 5/5 Complete 2026-04-30
- REQUIREMENTS.md — FS-SR-04 / FS-SR-05 / FS-SR-06 bullets [x]; traceability rows Complete
- STATE.md — milestone complete, 11/11 plans, 100%

---
*Phase: 04-flightsql-tpc-h-queries-against-external-starrocks-with-arro*
*Completed: 2026-04-30*
