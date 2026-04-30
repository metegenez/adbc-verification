---
phase: 04-flightsql-tpc-h-queries-against-external-starrocks-with-arro
reviewed: 2026-04-30T10:30:00Z
depth: standard
files_reviewed: 32
files_reviewed_list:
  - CLAUDE.md
  - benchmark/mysql-jdbc-vs-adbc.py
  - docker/docker-compose.yml
  - docker/generate-sf1-data.py
  - docker/init/sr-external/01-schema.sql
  - docker/init/sr-external/02-data.sql
  - pyproject.toml
  - queries/tpch/q01.sql
  - queries/tpch/q02.sql
  - queries/tpch/q03.sql
  - queries/tpch/q04.sql
  - queries/tpch/q05.sql
  - queries/tpch/q06.sql
  - queries/tpch/q07.sql
  - queries/tpch/q08.sql
  - queries/tpch/q09.sql
  - queries/tpch/q10.sql
  - queries/tpch/q11.sql
  - queries/tpch/q12.sql
  - queries/tpch/q13.sql
  - queries/tpch/q14.sql
  - queries/tpch/q15.sql
  - queries/tpch/q16.sql
  - queries/tpch/q17.sql
  - queries/tpch/q18.sql
  - queries/tpch/q19.sql
  - queries/tpch/q20.sql
  - queries/tpch/q21.sql
  - queries/tpch/q22.sql
  - run-verify.py
  - tests/test_benchmark_cli.py
  - tests/test_flightsql_starrocks.py
  - tests/test_queries.py
findings:
  critical: 0
  warning: 5
  info: 9
  total: 14
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-04-30T10:30:00Z
**Depth:** standard
**Files Reviewed:** 32
**Status:** issues_found

## Summary

Phase 4 introduces an `sr-external` StarRocks instance for end-to-end Arrow Flight verification, replaces the hand-rolled SF1 generator with the canonical DuckDB `tpch` extension, and consolidates 44 per-backend TPC-H query duplicates into a single canonical home at `queries/tpch/q01..q22.sql` with `{catalog}.{db}` placeholder substitution.

Overall the phase is well-structured: canonical query placeholders are consistent, the loader's substitution closes over a fixed allowlist (`CANONICAL_BACKENDS`) so SQL injection is bounded, defensive try/finally cleanup is present in every test, the `run-verify.py` service dict is correctly updated to include `sr-external`, and the schema/data init scripts respect the documented "no DUPLICATE KEY" pitfall.

The findings below are mostly hardening items: a brittle catalog-name regex, `str.format()` brace-collision risk if a future TPC-H query uses literal `{`/`}` (today's q01..q22 are clean — no instances found), and a few maintainability/clarity issues. There are **no critical or security issues** in this changeset.

## Warnings

### WR-01: `str.format()` placeholder substitution will crash on any future TPC-H query containing literal `{` or `}`

**File:** `tests/test_queries.py:197`
**Issue:** `_load_canonical` uses `path.read_text().format(catalog=catalog, db=db)`. Python's `str.format` treats every `{` and `}` as a format directive — any literal brace in a query body raises `KeyError`/`IndexError` at test-collection time. None of today's q01..q22 contain literal braces (verified with grep — all `{` matches are `{catalog}` or `{db}`), so the regression isn't live, but a future TPC-H query that legitimately uses brace characters (e.g., StarRocks struct literal, JSON predicate, or future TPC-H spec extension) will break collection across all backends, not just one. The failure surfaces as a parametrize-time `KeyError` with no file context, which is far harder to debug than a runtime SQL parse error.

**Fix:** Either escape braces (`.replace('{', '{{').replace('}', '}}')` for everything except `{catalog}`/`{db}` — clunky and error-prone) or replace `str.format` with explicit token replacement, mirroring the benchmark CLI's `rewrite_for_catalog`:
```python
def _load_canonical(query_name: str, backend: str) -> str:
    catalog, db = CANONICAL_BACKENDS[backend]
    path = CANONICAL_DIR / f"{query_name}.sql"
    return (
        path.read_text()
        .replace("{catalog}", catalog)
        .replace("{db}", db)
    )
```
This is what `benchmark/mysql-jdbc-vs-adbc.py:178-182` already does — keeping the two substitution paths consistent eliminates a future-divergence trap and removes the brace-collision footgun. The catalog/db values come from a closed dict, so the `replace` approach is no less safe than `format`.

### WR-02: `re.escape(backend)` on backend name is sufficient today but doesn't validate that `backend` is in the allowlist before regex use

**File:** `tests/test_queries.py:84-88`
**Issue:** `_expected_rows(sql, backend)` builds a regex from the caller-supplied `backend` string with `re.escape`, which is the right primitive — backend names like `flightsql-starrocks` contain a hyphen that's a metacharacter inside character classes (though not at top level). The escaping handles that correctly. However, `_expected_rows` is reachable from two call sites (`test_canonical_query` line 256 and indirectly), and the function does not assert that `backend in CANONICAL_BACKENDS`. If a caller passes an attacker-controlled string (today: only test parametrize, so bounded), the behavior is at worst a regex that doesn't match — but this is a defense-in-depth gap, not a live vulnerability.

**Fix:** Add a guard at the top of the function or document the precondition:
```python
def _expected_rows(sql: str, backend: str | None = None) -> int | None:
    if backend is not None and backend not in CANONICAL_BACKENDS:
        raise ValueError(f"unknown backend: {backend!r}")
    ...
```
Or, since `_expected_rows` is only ever called with known backends, leave a comment locking that contract. The `re.escape` itself is correct.

### WR-03: `_recover_fe()` in benchmark CLI calls `sys.exit(2)` from inside a retry loop — terminates the process before the outer retry can run

**File:** `benchmark/mysql-jdbc-vs-adbc.py:580-607`
**Issue:** `_recover_fe()` is invoked from `main()`'s retry loop (lines 528, 553, 574). On line 607 it calls `sys.exit(2)` if FE doesn't recover within 120s. Because `sys.exit` is invoked from inside the `for attempt in range(...)` loop in `main()`, this short-circuits the retry mechanism — the next attempt never runs even if `attempt < max_retries`. The CLI's docstring claims `max_retries = 3` but `_recover_fe()` makes that effectively a single shot once recovery starts failing.

**Fix:** Make `_recover_fe()` raise a recoverable exception or return a status, and let `main()` decide whether to abort:
```python
def _recover_fe() -> bool:
    """Restart sr-main and wait. Returns True if FE became ready, False otherwise."""
    ...
    while time.time() < deadline:
        try:
            ...
            return True
        except Exception:
            time.sleep(5)
    return False  # caller decides whether to retry or abort

# in main():
if not _recover_fe():
    if attempt < max_retries:
        continue  # try again
    sys.exit(2)
```
Alternatively, suppress the inner `sys.exit(2)` and just `return` so the outer loop runs another attempt against a still-broken FE (which will fail fast and re-enter recovery).

### WR-04: `_load_canonical` reads the canonical file twice in `test_canonical_query` — once via `_load_canonical` (line 252) and once directly (line 251)

**File:** `tests/test_queries.py:251-256`
**Issue:** `test_canonical_query` opens `queries/tpch/{query_name}.sql` twice in the same call:
```python
raw = (CANONICAL_DIR / f"{query_name}.sql").read_text()       # line 251
sql = _strip_comments(_load_canonical(query_name, backend))    # line 252  (also reads file)
```
`_load_canonical` (line 197) calls `path.read_text()` internally. With 22 queries × 3 backends = 66 test cases, this is 66 extra disk reads per test session. More importantly, if the file is mutated between line 251 and 252 (vanishingly unlikely on a test runner, but possible on shared CI), the parsed comments and the executed SQL will disagree silently, so the row-count assertion runs against stale Expected metadata.

**Fix:** Read once and pass through:
```python
canonical_path = CANONICAL_DIR / f"{query_name}.sql"
raw = canonical_path.read_text()
catalog, db = CANONICAL_BACKENDS[backend]
sql = _strip_comments(raw.replace("{catalog}", catalog).replace("{db}", db))
```
This also makes WR-01 trivially fixable in the same edit.

### WR-05: `parse_args()` in `run-verify.py` declares `--keep` and `--cleanup` mutually exclusive but both default to truthy values — `--cleanup` only takes effect at command-line time

**File:** `run-verify.py:60-71`
**Issue:** The `mutually_exclusive_group` declares `--keep` with `default=True` and `--cleanup` with `default=False`. After parsing, `args.keep` is always `True` (default + flag both produce `True`), so the post-test cleanup decision is gated solely on `args.cleanup`. If a future maintainer flips the defaults or adds a third flag, the mutex becomes silently broken because `argparse` doesn't enforce mutex on defaults — only on user-supplied flags. Today's behavior is correct (`--cleanup` is the only signal that matters), but the construct is misleading.

**Fix:** Drop the unused `--keep` flag (it's the implicit default — there's no scenario where the user explicitly passes `--keep`, since omitting `--cleanup` already keeps the stack), or replace the mutex with a single `--mode {keep,cleanup}` choice argument:
```python
parser.add_argument(
    "--mode",
    choices=["keep", "cleanup"],
    default="keep",
    help="Container lifecycle after tests (default: keep)",
)
# downstream:
if args.mode == "cleanup":
    _run_docker_compose(["down"])
```
This eliminates the dual-default confusion and makes the user-facing CLI semantically clearer.

## Info

### IN-01: `docker/generate-sf1-data.py` lacks the `lineterminator="\n"` safeguard called out in CLAUDE.md

**File:** `docker/generate-sf1-data.py:36-39`
**Issue:** CLAUDE.md "CSV line endings" pitfall (lines 158-160) explicitly warns that MySQL `LOAD DATA INFILE` corrupts the last column of each row when CSV uses CRLF. The new DuckDB-based generator delegates line-ending control to DuckDB's `COPY ... (FORMAT CSV)`, which on Linux defaults to LF (verified safe on the test platform), but there is no explicit option pinning this. If anyone runs the generator on Windows, or if a future DuckDB version changes the default, MySQL bulk load will silently corrupt data.

**Fix:** Add an explicit `LINE_ENDING` option to the COPY command (DuckDB ≥1.0 supports this):
```python
con.execute(
    f"COPY {table} TO '{out_path}' "
    f"(FORMAT CSV, HEADER TRUE, DELIMITER ',', LINE_ENDING 'unix')"
)
```
This makes the LF guarantee load-bearing in the file, not implicit in the runtime platform.

### IN-02: `_QUERY_FILENAME_RE` and the canonical loader assume `q\d{2}.sql` — query numbers ≥100 will silently skip

**File:** `benchmark/mysql-jdbc-vs-adbc.py:77` and `tests/test_queries.py:207`
**Issue:** TPC-H spec has 22 queries, so this is fine today, but the regex `r"^q(\d{2})\.sql$"` and the glob `CANONICAL_DIR.glob("q*.sql")` followed by `path.stem` slicing both assume two-digit numbering. If someone adds a `q23.sql` it works; `q100.sql` would be silently dropped by the benchmark CLI's regex (returns `None`) but picked up by `test_queries.py`'s glob (works). The two paths disagree on the supported numbering scheme.

**Fix:** Make the regex tolerate any digit count and document the convention in CLAUDE.md or `04-CANONICAL-SPEC.md`:
```python
_QUERY_FILENAME_RE = re.compile(r"^q(\d+)\.sql$")
```

### IN-03: `pyproject.toml` markers list includes `benchmark` but `tests/test_flightsql_starrocks.py` only uses `flightsql` marker — re-using the marker is intentional but undocumented

**File:** `pyproject.toml:21-31` + `tests/test_flightsql_starrocks.py:32, 64, 99, 132`
**Issue:** All four `test_flightsql_starrocks.py` tests carry `@pytest.mark.flightsql`, the same marker as `tests/test_flightsql.py` (sqlflite path). This is intentional per the phase plan (both are "FlightSQL backend tests"), and matches the docstring at line 1-9. However, there's no marker that distinguishes the StarRocks-Arrow-Flight path from the sqlflite path, so `pytest -m flightsql` runs both. If a contributor later wants to run only one, they need `pytest -m flightsql -k "starrocks"` or `... -k "not starrocks"`. Worth flagging for discoverability.

**Fix (optional):** Add a dedicated marker `flightsql_starrocks` or namespace it. Or simply note the dual-target behavior in the module docstring or CLAUDE.md test-pattern section. Not blocking.

### IN-04: `test_flightsql_sr_wrong_password` swallows all `pymysql.err.DatabaseError` exceptions — including unrelated FE errors

**File:** `tests/test_flightsql_starrocks.py:117-118`
**Issue:** The `try: create_adbc_catalog(...) except pymysql.err.DatabaseError: return` pattern accepts *any* `DatabaseError`, not just authentication failures. If FE is in a degraded state and CREATE CATALOG fails for a totally unrelated reason (e.g., the SIGSEGV-during-malformed-query pitfall called out in CLAUDE.md), this test passes when it shouldn't. The block comment says "Expected: fails at CREATE for StarRocks Arrow Flight" but doesn't pin the failure to the auth path.

**Fix:** Inspect the exception message for an auth-specific signal before treating it as a pass:
```python
except pymysql.err.DatabaseError as e:
    msg = str(e).lower()
    if "auth" in msg or "password" in msg or "unauthenticated" in msg or "permission" in msg:
        return  # expected
    raise  # something else broke — surface it
```
Acceptable to leave as-is if the comment is updated to acknowledge the trade-off (lifecycle test is broader anyway, so a degraded FE will be caught there first).

### IN-05: Bare `except Exception:` in `fe_alive` and `_recover_fe` swallow KeyboardInterrupt/SystemExit?

**File:** `benchmark/mysql-jdbc-vs-adbc.py:209-210, 604-605`
**Issue:** Both `fe_alive` and `_recover_fe` use bare `except Exception:` — modern Python correctly excludes `KeyboardInterrupt` and `SystemExit` from `Exception` (they inherit from `BaseException`), so this is technically safe. However, it does swallow `pymysql.err.OperationalError`, `socket.timeout`, and any unforeseen errors as "FE is down," masking root causes during debugging. In `_recover_fe`'s retry loop (line 591-605), the exception is silently slept-on without logging, so the user only sees the final 120s timeout message with no breadcrumbs.

**Fix:** Log the exception type and message when retrying so the caller has signal:
```python
except Exception as e:
    print(f"  ... waiting for FE: {type(e).__name__}: {e}", file=sys.stderr)
    time.sleep(5)
```

### IN-06: `_strip_sql_comments` and `_strip_comments` are duplicated across `benchmark/mysql-jdbc-vs-adbc.py:172-175` and `tests/test_queries.py:66-69`

**File:** `benchmark/mysql-jdbc-vs-adbc.py:172-175` + `tests/test_queries.py:66-69`
**Issue:** Both functions are identical:
```python
def _strip_comments(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()
```
Lives in two places with two different names (`_strip_sql_comments` vs `_strip_comments`). Both are private helpers; risk of divergence is low but real, especially as the canonical loader and benchmark CLI both consume the same `queries/tpch/` files.

**Fix:** Promote to `lib/sql_utils.py` (or extend `lib/catalog_helpers.py`):
```python
# lib/sql_utils.py
def strip_sql_comments(sql: str) -> str:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()
```
Then both consumers import it. Same edit could fold in `rewrite_for_catalog` since the test loader and benchmark CLI both perform the same `{catalog}.{db}` substitution.

### IN-07: `docker/init/sr-external/02-data.sql` re-runs TRUNCATE+INSERT on every container start — wastes ~2 min on every `up` even with warm volumes

**File:** `docker/init/sr-external/02-data.sql:7-85`
**Issue:** The init script header notes "Idempotent: TRUNCATE + re-import on every container start." However, since `sr-external` does not declare a named volume in `docker-compose.yml` (only the read-only bind mounts on lines 93-95 of `docker/docker-compose.yml`), the StarRocks data directory is *inside* the container's writable layer and is wiped on `docker compose down` (without -v) anyway. The TRUNCATE step is therefore mostly redundant — the table is already empty on cold start, and on warm restart it would still re-load. Plus, `docker-entrypoint-initdb.d` scripts in the StarRocks Dockerfile (which I haven't reviewed but is implied by the volume mount path) typically run only on first boot for upstream MySQL/Postgres images, but StarRocks' container behavior may differ. Worth verifying the script actually re-runs on warm boots; if not, the TRUNCATE is dead code.

**Fix:** If StarRocks' entrypoint re-runs init scripts on every boot, the current TRUNCATE+INSERT is correct (just slow). If it runs only on cold boot, drop the TRUNCATE. Document the actual entrypoint behavior in the file header to remove ambiguity. Either way, consider adding a sentinel check (`SELECT count(*) FROM region`) to skip the load if data is already present — that turns a 2-minute warm boot into a 1-second probe.

### IN-08: Magic ports `9408` and `9030` repeated across multiple files without a constant

**File:** `tests/test_queries.py:38, 50` + `tests/test_flightsql_starrocks.py:25` + `benchmark/mysql-jdbc-vs-adbc.py:60`
**Issue:** The Arrow Flight port `9408` and StarRocks MySQL-protocol port `9030` are inlined as string literals across multiple files. If StarRocks ever changes the default port or the deployment surfaces a non-default port, this requires search-and-replace across the suite. CLAUDE.md documents `9408` once, but the codebase doesn't centralize.

**Fix:** Promote to constants in `conftest.py` or a new `lib/ports.py`:
```python
SR_FLIGHT_PORT = 9408   # StarRocks FE Arrow Flight (sr-external internal, no host port)
SR_MYSQL_PORT  = 9030   # StarRocks FE MySQL protocol (sr-main published)
```
Low priority — current count is small and mostly in test fixtures.

### IN-09: `sr-external` start_period (180s) is shorter than `sr-mysql`/`sr-postgres` start_period (300s) but the SF1 lineitem load runs in both — revisit if cold boot starts timing out

**File:** `docker/docker-compose.yml:103`
**Issue:** `sr-mysql` and `sr-postgres` both use `start_period: 300s` to cover the SF1 lineitem load (see CLAUDE.md "MySQL healthcheck" pitfall: `start_period: 300s` covers the SF1 lineitem load. Don't shorten it.). `sr-external` uses `start_period: 180s` — half the budget. Native StarRocks `INSERT INTO ... SELECT * FROM FILES()` is generally faster than MySQL `LOAD DATA INFILE` (no row-by-row parsing, columnar ingestion), so 180s may be enough today. However, on slower CI hosts or on first-cold-start with both StarRocks instances loading from the same SF1 CSV bind mount in parallel, this could trip the wait loop in `run-verify.py` (which has its own 300s `HEALTHCHECK_TIMEOUT` at line 29 — so the runner won't time out, but the compose service will report "unhealthy" until it does come up).

**Fix:** Bump `sr-external` start_period to 300s for parity with the other backends, or add a comment justifying the shorter budget. Low priority.

---

_Reviewed: 2026-04-30T10:30:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
