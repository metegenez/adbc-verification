# Phase 03: Compare MySQL JDBC vs ADBC Reproducible Benchmark CLI - Pattern Map

**Mapped:** 2026-04-28
**Files analyzed:** 9 (5 new, 3 modified, 1 verified-no-change)
**Analogs found:** 8 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `benchmark/mysql-jdbc-vs-adbc.py` (new) | CLI entry / orchestrator | request-response (host -> StarRocks) | `/home/mete/coding/opensource/adbc_verification/run-verify.py` | exact (only argparse CLI in project) |
| `lib/catalog_helpers.py` (modify - add `create_jdbc_catalog`) | utility | request-response | `/home/mete/coding/opensource/adbc_verification/lib/catalog_helpers.py:6-40` (existing `create_adbc_catalog`) | exact (sibling function, same file) |
| `benchmark/__init__.py` (new, empty) | package marker | n/a | `/home/mete/coding/opensource/adbc_verification/lib/__init__.py` (0 lines) and `/home/mete/coding/opensource/adbc_verification/tests/__init__.py` (0 lines) | exact |
| EXPLAIN ANALYZE parser (inline in CLI per RESEARCH.md - or `benchmark/explain_parser.py` if grows >150 lines) | utility | transform | `/home/mete/coding/opensource/adbc_verification/tests/test_queries.py:31-46` (regex parse helpers) | role-match (regex over text) |
| ASCII table renderer (inline in CLI per RESEARCH.md) | utility | transform | none in codebase - use stdlib f-strings (RESEARCH.md "Don't Hand-Roll" + "ASCII table rendering recommendation" decided no library) | no analog |
| `tests/test_benchmark_cli.py` (new) | test | request-response | `/home/mete/coding/opensource/adbc_verification/tests/test_mysql.py:44-66` (catalog lifecycle pattern) and `/home/mete/coding/opensource/adbc_verification/tests/test_negative.py:29-64` (error-path pattern) | role-match |
| `docker/drivers/mysql-connector-j-9.3.0.jar` (new artifact, not committed - see A1) | binary artifact | n/a | `/home/mete/coding/opensource/adbc_verification/docker/drivers/libadbc_driver_mysql.so` (not committed - see `.gitignore:9`) | exact (mirror `.so` convention) |
| `docker/Dockerfile` (verified - **no change required**) | config | n/a | `/home/mete/coding/opensource/adbc_verification/docker/Dockerfile:18` (existing `COPY drivers/`) | exact (already covers JAR) |
| `pyproject.toml` (verified - **no change required**) | config | n/a | `/home/mete/coding/opensource/adbc_verification/pyproject.toml:6-10` (3 deps - argparse/re/statistics are stdlib) | n/a |

**Decision flags surfaced for the planner:**
- **JAR commit policy:** `.gitignore:9` excludes the entire `docker/drivers/` directory; therefore `mysql-connector-j-*.jar` will NOT be committed by default. RESEARCH.md A1 assumed it would be committed; reality is the opposite. Planner must either (a) add the JAR explicitly to `.gitignore` (or document expectation that contributors download via curl), or (b) un-ignore `docker/drivers/*.jar` if the team wants to commit it. **Recommend (a)** - it mirrors the existing `.so` flow; a small `docker/fetch-jdbc-jar.sh` (or curl one-liner in README/CLAUDE.md) is the established convention.
- **Property key:** ADBC catalog uses `username` (CLAUDE.md "Key Rules"), JDBC catalog uses `user` (RESEARCH.md "Specific Topic Findings #1"). The new `create_jdbc_catalog` helper must use `user` and the docstring must call out the difference.
- **`__init__.py`:** Project convention is empty `__init__.py` files (verified: `lib/__init__.py` and `tests/__init__.py` are 0 bytes). New `benchmark/__init__.py` should also be empty - or omitted entirely if the CLI is invoked as a script (`.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py`) rather than imported. **Recommend omitting** since `run-verify.py` lives at root with no `__init__.py` and the new CLI mirrors that.

## Pattern Assignments

### `benchmark/mysql-jdbc-vs-adbc.py` (CLI entry, request-response)

**Analog:** `/home/mete/coding/opensource/adbc_verification/run-verify.py`

**Imports pattern** (`run-verify.py:14-24`):
```python
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
```
**Apply to new CLI:** Drop `shutil`, `subprocess`, `time`, `datetime`. Add `re` (EXPLAIN ANALYZE parsing), `statistics` (geometric_mean), and `pymysql` (StarRocks connection). Also import `from lib.catalog_helpers import create_adbc_catalog, drop_catalog` plus the new `create_jdbc_catalog` once added.

**Module-level constants pattern** (`run-verify.py:26-30`):
```python
COMPOSE_DIR = pathlib.Path(__file__).resolve().parent / "docker"
REPORTS_DIR = pathlib.Path(__file__).resolve().parent / "reports"
DEFAULT_REPORT = "reports/latest.json"
HEALTHCHECK_TIMEOUT = 300
HEALTHCHECK_POLL_INTERVAL = 3
```
**Apply to new CLI:** Use the same idiom: `QUERIES_DIR = pathlib.Path(__file__).resolve().parent.parent / "queries" / "mysql"`, `MYSQL_JDBC_JAR = "/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"`, `MYSQL_ADBC_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"`, `MYSQL_URI_ADBC = "mysql://root:testpass@sr-mysql:3306/testdb"`, `MYSQL_URI_JDBC = "jdbc:mysql://sr-mysql:3306/testdb"`. Match the SCREAMING_SNAKE_CASE constant convention.

**main() + try/except wrapper pattern** (`run-verify.py:33-49`):
```python
def main() -> None:
    args = parse_args()

    try:
        result = run_verification(args)
        sys.exit(0 if result else 1)
    except subprocess.CalledProcessError as e:
        print(f"\n✗ Command failed: {e}", file=sys.stderr)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        if args.cleanup:
            _run_docker_compose(["down"])
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
```
**Apply to new CLI:** Same outer try/except shape, but the `KeyboardInterrupt` branch must `drop_catalog(conn, "bench_jdbc"); drop_catalog(conn, "bench_adbc")` (Pitfall 5). The `subprocess.CalledProcessError` arm is N/A - benchmark doesn't shell out. Add a `pymysql.err.OperationalError` arm for "FE went away" (CLAUDE.md FE SIGSEGV pitfall) that prints the recovery hint.

**parse_args() pattern** (`run-verify.py:52-90`):
```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StarRocks ADBC Verification Suite — ship→verify→retest loop",
    )
    parser.add_argument("fe_deb", help="Path to starrocks-fe .deb package")
    parser.add_argument("be_deb", help="Path to starrocks-be .deb package")
    ...
    parser.add_argument(
        "--report",
        metavar="FILE",
        default=DEFAULT_REPORT,
        help=f"Write JSON report to FILE (default: {DEFAULT_REPORT})",
    )
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Skip docker compose build (reuse existing images)",
    )

    return parser.parse_args()
```
**Apply to new CLI:** Same docstring placement, same `--flag` style with `default=` and `help=` strings. New flags per D-04: `--scale` (default `"sf1"`), `--queries` (default `"all"`), `--runs` (`type=int`, default `3`), `--timeout` (`type=int`, default `60`). Mirror the `description="..."` first arg.

**Reporting / final-print pattern** (`run-verify.py:287-298`):
```python
def _print_report(args: argparse.Namespace, test_passed: bool, summary: dict) -> None:
    fe_name = pathlib.Path(args.fe_deb).name
    be_name = pathlib.Path(args.be_deb).name
    print()
    print("═══════════════════════════════════════════")
    print(" Verification Complete")
    print("═══════════════════════════════════════════")
    print(f" DEB: {fe_name}, {be_name}")
    print(f" Result: {'✓ PASSED' if test_passed else '✗ FAILED'}")
    print(f" Report: {summary['report_file']}")
    print(f" Containers: {summary['containers']}")
```
**Apply to new CLI:** Use the same `═══` banner style for the benchmark summary header (StarRocks version + scale + run count) printed BEFORE the table, and a matching trailing banner. The table itself goes between (rendered via stdlib f-strings per RESEARCH.md "ASCII table rendering recommendation").

**Project conventions to copy:**
- Shebang `#!/usr/bin/env python3` at line 1 (`run-verify.py:1`)
- Module docstring with usage examples (`run-verify.py:2-12`)
- `from __future__ import annotations` (`run-verify.py:14`)
- `if __name__ == "__main__": main()` at end (`run-verify.py:300-301`)

---

### `lib/catalog_helpers.py` extension - new function `create_jdbc_catalog` (utility, request-response)

**Analog:** existing `create_adbc_catalog` in the same file (`lib/catalog_helpers.py:6-40`)

**Full sibling function to copy** (`lib/catalog_helpers.py:6-40`):
```python
def create_adbc_catalog(
    conn,
    catalog_name: str,
    driver_url: str,
    uri: str = "",
    extra_props: dict | None = None,
    entrypoint: str = "",
) -> None:
    """Issue ``CREATE EXTERNAL CATALOG`` via the given pymysql connection.

    *driver_url* is the filesystem path to the ADBC driver ``.so``.
    Optional *uri* sets the ``uri`` property (e.g. a connection string).
    Optional *entrypoint* sets ``driver_entrypoint`` (required for DuckDB).
    *extra_props* are merged into the ``PROPERTIES(...)`` clause.
    """
    props: dict[str, str] = {
        "type": "adbc",
        "driver_url": driver_url,
    }
    if uri:
        props["uri"] = uri
    if entrypoint:
        props["driver_entrypoint"] = entrypoint
    if extra_props:
        props.update(extra_props)

    # Escape double quotes in values. Newlines are kept raw — StarRocks SQL
    # accepts them inside quoted property values (needed for PEM certificates).
    def _escape(v: str) -> str:
        return v.replace('"', '\\"')

    props_sql = ", ".join(f'"{k}"="{_escape(v)}"' for k, v in props.items())
    sql = f"CREATE EXTERNAL CATALOG {catalog_name} PROPERTIES({props_sql})"
    with conn.cursor() as cur:
        cur.execute(sql)
```

**Apply to new function:** Copy the exact shape, change defaults and properties:
```python
def create_jdbc_catalog(
    conn,
    catalog_name: str,
    jdbc_uri: str,
    user: str,
    password: str,
    driver_url: str,
    driver_class: str = "com.mysql.cj.jdbc.Driver",
) -> None:
    """Issue ``CREATE EXTERNAL CATALOG`` for a JDBC source via pymysql.

    Property key is ``user`` (NOT ``username`` - that is ADBC-specific).
    Properties: type, user, password, jdbc_uri, driver_url, driver_class.
    """
    props: dict[str, str] = {
        "type": "jdbc",
        "user": user,
        "password": password,
        "jdbc_uri": jdbc_uri,
        "driver_url": driver_url,
        "driver_class": driver_class,
    }

    def _escape(v: str) -> str:
        return v.replace('"', '\\"')

    props_sql = ", ".join(f'"{k}"="{_escape(v)}"' for k, v in props.items())
    sql = f"CREATE EXTERNAL CATALOG {catalog_name} PROPERTIES({props_sql})"
    with conn.cursor() as cur:
        cur.execute(sql)
```

**Reuse-don't-duplicate** (CLAUDE.md "All catalog interactions go through lib/catalog_helpers.py"):
- `drop_catalog(conn, "bench_jdbc")` already exists at `lib/catalog_helpers.py:43-46` - use it as-is
- `execute_sql(conn, sql)` already exists at `lib/catalog_helpers.py:56-60` - use it as-is for running EXPLAIN ANALYZE

---

### EXPLAIN ANALYZE parser (utility, transform)

**Analog (closest in codebase):** `/home/mete/coding/opensource/adbc_verification/tests/test_queries.py:31-46`

```python
def _strip_comments(sql: str) -> str:
    """Remove SQL comment lines (lines starting with --)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def _expected_rows(sql: str) -> int | None:
    """Parse ``-- Expected: N rows`` from a .sql file, return N or None."""
    m = re.search(r"--\s*Expected:\s*(\d+)\s+rows?", sql)
    return int(m.group(1)) if m else None


def _skip_reason(sql: str) -> str | None:
    """Parse ``-- Skip: <reason>`` from a .sql file, return the reason or None."""
    m = re.search(r"--\s*Skip:\s*(.+)", sql)
    return m.group(1).strip() if m else None
```

**Pattern to copy:**
- Underscore-prefix for module-private parsers: `_strip_ansi`, `_parse_summary_total`, `_parse_scan_nodes`, `_parse_duration_ns`
- Single-purpose function with `re` module-level pattern + brief docstring + Optional return type
- The `re.search` + `m.group(1)` idiom for extraction
- Return `None` (or raise) when the pattern isn't found - caller decides

**Concrete parser bodies are pre-validated in RESEARCH.md `Code Examples` section (lines 569-621).** Planner should copy the exact bodies for `_DUR_SEG`, `_UNIT_NS`, `parse_duration_ns`, `parse_summary_total`, `parse_scan_nodes`, `with_timeout_hint`. RESEARCH.md is the source of truth for the regex correctness; the project-style helpers above are the wrapping convention.

**Reuse `_skip_reason`** (Pitfall 6 in RESEARCH.md): RESEARCH.md recommends factoring `_skip_reason` from `tests/test_queries.py:43-46` into `lib/query_helpers.py` and reusing in the CLI. **Lower-friction alternative:** define a constant copy of the same 4 lines in the CLI - 4-line duplication is cheaper than introducing a new shared module right now. Planner picks.

---

### ASCII table renderer (utility, transform)

**Analog:** none in codebase. RESEARCH.md "ASCII table rendering recommendation" (lines 718-722) decided NO library, stdlib f-strings only.

**Reference implementation already provided in RESEARCH.md `Code Examples`** (lines 650-662):
```python
def render_table(rows: list[dict], cols: list[tuple[str, int]]) -> str:
    """rows is a list of dicts; cols is [(label, width), ...]."""
    sep = "+".join("-" * (w + 2) for _, w in cols)
    sep = f"+{sep}+"
    out = [sep]
    out.append("| " + " | ".join(f"{lbl:<{w}}" for lbl, w in cols) + " |")
    out.append(sep)
    for r in rows:
        out.append("| " + " | ".join(f"{r[lbl]!s:<{w}}" for lbl, w in cols) + " |")
    out.append(sep)
    return "\n".join(out)
```
**Project style note:** Match `run-verify.py:287-298`'s use of `print()` rather than building one giant string - call `print(render_table(...))` once at the end. AVG/GEOMEAN summary rows (D-10) are appended to the same `rows` list before rendering with no separator (or a `==` separator if the planner wants it visually distinct).

---

### `tests/test_benchmark_cli.py` (test, request-response)

**Analogs:**
- `/home/mete/coding/opensource/adbc_verification/tests/test_mysql.py:44-66` - catalog lifecycle smoke pattern
- `/home/mete/coding/opensource/adbc_verification/tests/test_negative.py:29-64` - error-path validation pattern

**Imports pattern** (`tests/test_mysql.py:1-18`):
```python
"""MySQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data round-trip, show tables, negative, pass-
through). Uses the sr-mysql Docker Compose service as the backend. Test data
is pre-loaded via MySQL init scripts.
"""

from __future__ import annotations

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)
```
**Apply to new test:** Same module-docstring style at top. Import `create_jdbc_catalog` once added; import `subprocess` and `sys` for the smoke test that runs the CLI.

**Lifecycle pattern with try/finally** (`tests/test_mysql.py:44-66`):
```python
@pytest.mark.mysql
def test_mysql_catalog_lifecycle(sr_conn, mysql_driver_path, mysql_port):
    """CREATE CATALOG -> SHOW CATALOGS -> SHOW DATABASES -> DROP CATALOG."""
    cat = "test_mysql_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=mysql_driver_path,
            uri=_MYSQL_URI,
        )
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Expected '{cat}' in {catalogs}"
        ...
        drop_catalog(sr_conn, cat)
        catalogs_after = show_catalogs(sr_conn)
        assert cat not in catalogs_after, f"'{cat}' still in catalogs after drop"
    finally:
        drop_catalog(sr_conn, cat)
```
**Apply to new test:** Mirror the try/finally + `drop_catalog` in `finally` shape. Test names: `test_create_jdbc_catalog_lifecycle` (verify the new helper produces a working `bench_jdbc` catalog), `test_explain_analyze_parser_returns_total_ns_for_q01` (run actual EXPLAIN ANALYZE through the CLI's parser, assert int > 0), and `test_benchmark_cli_smoke_runs_one_query` (subprocess.run of `.venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries 1 --runs 1`, assert returncode == 0 and stdout contains expected table headers).

**Use marker** (`tests/test_mysql.py:44`):
```python
@pytest.mark.mysql
```
**Apply:** Either reuse `@pytest.mark.mysql` (since the benchmark backend IS MySQL) OR add a new marker `benchmark` in `pyproject.toml:20-29` markers section. Match other markers' `name: description` form. Recommend `benchmark` since it's a separate concern from ADBC verification tests.

**Smoke-test of CLI via subprocess pattern** - no exact analog in codebase; closest is `run-verify.py:253-267` (`_run_tests` invokes pytest as subprocess):
```python
def _run_tests(args: argparse.Namespace) -> bool:
    pytest_cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--json-report",
        f"--json-report-file={args.report}",
    ]
    if args.subset:
        pytest_cmd.extend(["-k", args.subset])

    result = subprocess.run(pytest_cmd)
    return result.returncode == 0
```
**Apply to smoke test:** Same `subprocess.run([sys.executable, ...])` shape. Note CLAUDE.md "Pitfalls - run-verify.py quirks" warns that `sys.executable` is system Python; for the test, use `sys.executable` since pytest itself runs under `.venv` so `sys.executable` IS `.venv/bin/python` in that context. The CLI being tested doesn't need pytest, so the import-availability concern doesn't apply.

---

### `docker/drivers/mysql-connector-j-9.3.0.jar` (binary artifact)

**Analog:** `docker/drivers/libadbc_driver_mysql.so` (and the four other `.so` files listed in `.gitignore:9` which excludes the entire `docker/drivers/` directory)

**Pattern observed:**
- Existing `.so` files live in `docker/drivers/` (host)
- They are NOT committed to git (`.gitignore:9` excludes `docker/drivers/`)
- They are copied to `/opt/starrocks/drivers/` at image build time via `Dockerfile:18` (`COPY drivers/ /opt/starrocks/drivers/`)
- Setup is documented in `CLAUDE.md` "Prerequisites" line: `Driver .so files in docker/drivers/ (copy from ~/.config/adbc/drivers/)`

**Apply to new JAR:**
- Place `mysql-connector-j-9.3.0.jar` in `docker/drivers/` on the host
- It will be picked up automatically by the existing `Dockerfile:18` `COPY drivers/` line - **no Dockerfile change required** (verified by RESEARCH.md "Standard Stack — Dockerfile change: None required" and Dockerfile inspection)
- Document in CLAUDE.md "Prerequisites" the new requirement: `MySQL Connector/J JAR in docker/drivers/ (curl from Maven Central)`
- Add a fetch script or one-line curl in CLAUDE.md mirroring the `dbc install` line pattern. RESEARCH.md provides the verified URL: `https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/9.3.0/mysql-connector-j-9.3.0.jar`

**Path used by JDBC catalog SQL:** `/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar` (RESEARCH.md Pitfall 2 - no glob expansion; pin exact filename)

---

### `docker/Dockerfile` (verified - **no change required**)

**Existing line `Dockerfile:18`:**
```dockerfile
COPY drivers/ /opt/starrocks/drivers/
```
This copies everything in `docker/drivers/` regardless of file extension. The new JAR is automatically included. Confirmed by both RESEARCH.md ("Dockerfile change: None required") and direct file inspection.

**No edits to Dockerfile required.** The planner should explicitly verify this in the plan and not silently leave a Dockerfile-edit task.

---

### `pyproject.toml` (verified - **no change required**)

**Existing deps** (`pyproject.toml:6-10`):
```toml
dependencies = [
    "pytest>=8.0",
    "pymysql>=1.1",
    "pytest-json-report>=1.5",
]
```
**Phase 3 imports:** `argparse`, `re`, `statistics`, `pathlib`, `sys`, `pymysql` - all stdlib except `pymysql` which is already listed. No additions required (verified by RESEARCH.md "Standard Stack: no new deps").

**Markers section** (`pyproject.toml:20-29`) - planner may add a new `benchmark` marker per the test classification above. That IS a `pyproject.toml` edit, but it's a one-liner inside the `markers = [...]` array, not a dependency change.

---

## Shared Patterns

### Pattern: Try/finally catalog teardown (cross-cutting, applies to CLI main + every test)

**Source:** `lib/catalog_helpers.py:43-46` (`drop_catalog` is idempotent via `IF EXISTS`)
```python
def drop_catalog(conn, catalog_name: str) -> None:
    """Issue ``DROP CATALOG IF EXISTS``."""
    with conn.cursor() as cur:
        cur.execute(f"DROP CATALOG IF EXISTS {catalog_name}")
```
**Source:** `tests/test_mysql.py:65-66`
```python
    finally:
        drop_catalog(sr_conn, cat)
```
**Apply to:**
- `benchmark/mysql-jdbc-vs-adbc.py` `main()` - wrap the entire benchmark loop in try/finally that drops both `bench_jdbc` and `bench_adbc` (Pitfall 5: catalog leak on Ctrl+C). Add a `KeyboardInterrupt` arm that calls the same drops then exits 130. **Belt-and-suspenders:** call `drop_catalog` BEFORE create as well, to recover from prior dirty state.
- `tests/test_benchmark_cli.py` - every test that creates a catalog needs the same try/finally.

---

### Pattern: pymysql connection setup (StarRocks)

**Source:** `conftest.py:73-84`
```python
@pytest.fixture(scope="session")
def sr_conn():
    """Connect to StarRocks FE via STARROCKS_HOST:STARROCKS_PORT."""
    conn = pymysql.connect(
        host=STARROCKS_HOST,
        port=STARROCKS_PORT,
        user="root",
        password="",
        autocommit=True,
    )
    yield conn
    conn.close()
```
**Source:** `conftest.py:21-22` for env var read:
```python
STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))
```
**Apply to:** `benchmark/mysql-jdbc-vs-adbc.py` should read the same `STARROCKS_HOST` / `STARROCKS_PORT` env vars with the same defaults and connect with the same `user="root", password="", autocommit=True` triple. The CLI is host-side just like pytest, so the connection idiom is identical. CLAUDE.md "Docker Compose is the only execution path" is satisfied because the CLI talks to the running compose stack, not to an embedded StarRocks.

---

### Pattern: Constant URIs / driver paths (compose-style)

**Source:** `tests/test_mysql.py:24-27`
```python
MYSQL_USER = "root"
MYSQL_PASS = "testpass"
MYSQL_DB = "testdb"
_MYSQL_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASS}@sr-mysql:3306/{MYSQL_DB}"
```
**Source:** `conftest.py:32` (driver constant pattern)
```python
MYSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
```
**Apply to:** `benchmark/mysql-jdbc-vs-adbc.py` should define module-level constants in the same SCREAMING_SNAKE_CASE style:
```python
MYSQL_USER = "root"
MYSQL_PASS = "testpass"
MYSQL_DB = "testdb"
MYSQL_HOST_INTERNAL = "sr-mysql:3306"  # Docker DNS, internal port

ADBC_DRIVER_PATH = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
ADBC_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASS}@{MYSQL_HOST_INTERNAL}/{MYSQL_DB}"

JDBC_DRIVER_PATH = "/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"
JDBC_URI = f"jdbc:mysql://{MYSQL_HOST_INTERNAL}/{MYSQL_DB}"
JDBC_DRIVER_CLASS = "com.mysql.cj.jdbc.Driver"
```
The naming `_MYSQL_URI` (with leading underscore) in `tests/test_mysql.py:27` is a pytest module-private convention; the CLI is a script not a module so the constants don't need underscore-prefixing.

---

### Pattern: Project header / docstring style

**Source:** `run-verify.py:1-13`
```python
#!/usr/bin/env python3
"""StarRocks ADBC Verification Suite — ship→verify→retest loop.

Copies StarRocks .deb packages, builds Docker Compose containers, waits for
healthchecks, runs the pytest test suite, captures logs on failure, and
reports results.

Usage:
    ./run-verify.py /path/to/starrocks-fe.deb /path/to/starrocks-be.deb
    ./run-verify.py --subset flightsql fe.deb be.deb
    ./run-verify.py --cleanup --report results.json fe.deb be.deb
"""
```
**Apply to new CLI:** Same shebang + module docstring with a short paragraph + `Usage:` block listing 2-3 example invocations (covers `--queries`, `--runs`, `--scale`). Document the `.venv/bin/python` requirement in the Usage block (CLAUDE.md "Pitfalls - run-verify.py quirks" notes the system-Python trap).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| ASCII table renderer (inline) | utility | transform | The codebase has no ASCII table emitter. RESEARCH.md decided no library; the reference impl in RESEARCH.md `Code Examples` (lines 650-662) is the source of truth. |
| EXPLAIN ANALYZE parser | utility | transform (text -> structured) | The codebase has no EXPLAIN handling; closest is `tests/test_queries.py:31-46` regex helpers (style/wrapper analog only - not the parsing logic itself). The parser bodies in RESEARCH.md `Code Examples` (lines 575-619) are pre-validated against the live container and should be copied verbatim. |

## Metadata

**Analog search scope:**
- `/home/mete/coding/opensource/adbc_verification/` (project root)
- `/home/mete/coding/opensource/adbc_verification/lib/`
- `/home/mete/coding/opensource/adbc_verification/tests/`
- `/home/mete/coding/opensource/adbc_verification/queries/mysql/`
- `/home/mete/coding/opensource/adbc_verification/docker/`

**Files scanned (read in full or grep-targeted):**
- `run-verify.py` (302 lines, full)
- `lib/catalog_helpers.py` (60 lines, full)
- `lib/__init__.py` (0 bytes, full)
- `tests/__init__.py` (0 bytes, full)
- `tests/test_queries.py` (160 lines, full)
- `tests/test_mysql.py` (188 lines, full)
- `tests/test_postgres.py` (lines 1-100, head)
- `tests/test_negative.py` (lines 1-80, head)
- `conftest.py` (220 lines, full)
- `pyproject.toml` (29 lines, full)
- `docker/Dockerfile` (24 lines, full)
- `docker/docker-compose.yml` (89 lines, full)
- `.gitignore` (15 lines, full)
- `queries/mysql/03-q01-pricing-summary.sql`, `03-q03-shipping-priority.sql` (sample queries, full)
- `docker/generate-sf1-data.py` (head only - confirms script-style, stdlib-only convention)
- Project-wide grep for `argparse`, `EXPLAIN`, `ASCII|tabulate|render`

**Pattern extraction date:** 2026-04-28
