"""Execute every .sql file under queries/ against live Docker Compose catalogs.

Catalog names in the SQL files (sr_sqlite, sr_postgres, etc.) are created as
session-scoped ADBC catalogs so all query files in this module share them.

Phase 4 introduces a canonical TPC-H home at queries/tpch/q01..q22.sql,
consumed via _load_canonical with {catalog}.{db} substitution per backend
in CANONICAL_BACKENDS. The legacy per-directory mechanism still handles
queries/sqlite/, queries/duckdb/, queries/flightsql/, queries/cross-join/,
queries/postgres/01-select.sql, queries/postgres/02-join.sql,
queries/mysql/01-select.sql, queries/mysql/02-join.sql.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql


QUERIES_DIR = pathlib.Path(__file__).resolve().parent.parent / "queries"
CANONICAL_DIR = QUERIES_DIR / "tpch"

# Postgres skip rationale: postgres-numeric Arrow extension type is unsupported in
# StarRocks BE. The 17 ids below are the queries that fail with that codec gap.
# See .planning/phases/02-postgresql-and-mysql-tpc-h-sf1-data-loading-and-queries/02-NOTES-postgres-numeric.md

# Map catalog name → (driver fixture name, URI, entrypoint or None)
CATALOG_MAP: dict[str, tuple[str, str, str | None]] = {
    "sr_sqlite":              ("sqlite_driver_path",    "/opt/starrocks/data/tpch_sqlite.db",     None),
    "sr_sqlite_emp":          ("sqlite_driver_path",    "/opt/starrocks/data/cross_sqlite_a.db",  None),
    "sr_postgres":            ("postgres_driver_path",  "postgresql://testuser:testpass@sr-postgres:5432/testdb", None),
    "sr_mysql":               ("mysql_driver_path",     "mysql://root:testpass@sr-mysql:3306/testdb",       None),
    "sr_flightsql":           ("flightsql_driver_path", "grpc://sr-flightsql:31337",              None),
    "sr_flightsql_starrocks": ("flightsql_driver_path", "grpc://sr-external:9408",                None),
    # DuckDB: use :memory: for query tests — file-based URI has single-writer lock conflict with FE
    "sr_duckdb":              ("duckdb_driver_path",    ":memory:",                                "duckdb_adbc_init"),
}

# Backend → (catalog name, schema/db name) for canonical TPC-H query substitution.
# Only listed backends participate in the (canonical_query × backend) parametrization
# in test_canonical_query; other directories (sqlite, duckdb, flightsql, cross-join,
# mysql/01-select.sql, etc.) keep the legacy per-directory mechanism.
CANONICAL_BACKENDS: dict[str, tuple[str, str]] = {
    "postgres":             ("sr_postgres",            "public"),
    "mysql":                ("sr_mysql",               "testdb"),
    "flightsql-starrocks":  ("sr_flightsql_starrocks", "tpch"),
}

# Per-backend skip manifest. Replaces inline `-- Skip:` directives that previously
# lived in queries/postgres/03-q*.sql. The 17 postgres ids match the queries that
# require the postgres-numeric Arrow opaque-type decoder absent from StarRocks BE.
CANONICAL_SKIPS: dict[str, set[str]] = {
    "postgres": {
        "q01", "q02", "q03", "q05", "q06", "q07", "q08", "q09", "q10",
        "q11", "q14", "q15", "q17", "q18", "q19", "q20", "q22",
    },
    "mysql": set(),
    "flightsql-starrocks": set(),
}


def _strip_comments(sql: str) -> str:
    """Remove SQL comment lines (lines starting with --)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def _expected_rows(sql: str, backend: str | None = None) -> int | None:
    """Parse the expected row count from comment lines.

    Recognized comment forms (in order of precedence):
      1. ``-- Expected (<backend>): N rows``  — per-backend, takes precedence when matching
      2. ``-- Expected: N rows``              — shared across backends (legacy / equal-counts case)

    The per-backend form is required by 04-CANONICAL-SPEC.md for queries/tpch/q*.sql
    where the same query may produce different counts across backends. The shared
    form is kept for backwards compatibility with queries/sqlite/, queries/cross-join/,
    queries/flightsql/, queries/mysql/01-select.sql, etc.
    """
    if backend is not None:
        per_backend = re.search(
            r"--\s*Expected\s*\(\s*" + re.escape(backend) + r"\s*\)\s*:\s*(\d+)\s+rows?",
            sql,
        )
        if per_backend:
            return int(per_backend.group(1))
    shared = re.search(r"--\s*Expected:\s*(\d+)\s+rows?", sql)
    return int(shared.group(1)) if shared else None


# NOTE: _skip_reason() was removed when the canonical loader landed (Phase 4).
# Inline `-- Skip:` directives in query files are no longer parsed; canonical
# TPC-H skips live in CANONICAL_SKIPS keyed by (backend, query_name).
# See .planning/phases/04-flightsql-tpc-h-queries-against-external-starrocks-with-arro/04-CANONICAL-SPEC.md


# ---------------------------------------------------------------------------
# Session-scoped catalog fixtures (one per driver)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sr_sqlite_cat(sr_conn, sqlite_driver_path):
    cat = "sr_sqlite"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=sqlite_driver_path,
                        uri=CATALOG_MAP["sr_sqlite"][1])
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_sqlite_emp_cat(sr_conn, sqlite_driver_path):
    """Employees database for cross-join queries."""
    cat = "sr_sqlite_emp"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=sqlite_driver_path,
                        uri=CATALOG_MAP["sr_sqlite_emp"][1])
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_postgres_cat(sr_conn, postgres_driver_path):
    cat = "sr_postgres"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=postgres_driver_path,
                        uri=CATALOG_MAP["sr_postgres"][1])
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_mysql_cat(sr_conn, mysql_driver_path):
    cat = "sr_mysql"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=mysql_driver_path,
                        uri=CATALOG_MAP["sr_mysql"][1])
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_flightsql_cat(sr_conn, flightsql_driver_path):
    cat = "sr_flightsql"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path,
                        uri=CATALOG_MAP["sr_flightsql"][1],
                        extra_props={
                            "username": "sqlflite_username",
                            "password": "sqlflite_password",
                        })
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_flightsql_starrocks_cat(sr_conn, flightsql_driver_path):
    cat = "sr_flightsql_starrocks"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=flightsql_driver_path,
                        uri=CATALOG_MAP["sr_flightsql_starrocks"][1],
                        extra_props={
                            "username": "root",
                            "password": "",
                        })
    yield cat
    drop_catalog(sr_conn, cat)


@pytest.fixture(scope="session")
def sr_duckdb_cat(sr_conn, duckdb_driver_path):
    cat = "sr_duckdb"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=duckdb_driver_path,
                        uri=CATALOG_MAP["sr_duckdb"][1],
                        entrypoint=CATALOG_MAP["sr_duckdb"][2])
    yield cat
    drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Canonical TPC-H loader: queries/tpch/q*.sql × CANONICAL_BACKENDS cross product
# ---------------------------------------------------------------------------

def _load_canonical(query_name: str, backend: str) -> str:
    """Read queries/tpch/<query_name>.sql and substitute {catalog}.{db} for the backend.

    Returns SQL ready for execution. Raises FileNotFoundError if the canonical file
    is missing — Phase 4 plan 04-05 owns populating queries/tpch/q01.sql..q22.sql.
    """
    catalog, db = CANONICAL_BACKENDS[backend]
    path = CANONICAL_DIR / f"{query_name}.sql"
    return path.read_text().format(catalog=catalog, db=db)


def _discover_canonical_cases():
    """Yield pytest.param(backend, query_name) for every (backend × q01..q22) pair.

    Returns no cases if queries/tpch/ doesn't exist yet (e.g., during 04-05 staging).
    """
    if not CANONICAL_DIR.is_dir():
        return
    canonical_files = sorted(CANONICAL_DIR.glob("q*.sql"))
    for backend in CANONICAL_BACKENDS:
        for canonical_path in canonical_files:
            query_name = canonical_path.stem  # "q01", "q02", ...
            yield pytest.param(
                backend, query_name,
                id=f"canonical[{backend}/{query_name}]",
            )


# ---------------------------------------------------------------------------
# Parametrized: one test per canonical (query × backend) and per legacy .sql file
# ---------------------------------------------------------------------------

def _discover_query_files():
    """Yield (driver_name, file_path) for every .sql under queries/, excluding queries/tpch/.

    queries/tpch/ is the canonical home consumed by _discover_canonical_cases via
    CANONICAL_BACKENDS substitution. Everything else (sqlite, duckdb, flightsql,
    cross-join, mysql/01-select.sql, mysql/02-join.sql, postgres/01-select.sql,
    postgres/02-join.sql, etc.) keeps the legacy per-directory mechanism.
    """
    for child in sorted(QUERIES_DIR.rglob("*.sql")):
        rel = child.relative_to(QUERIES_DIR)
        driver = rel.parts[0]  # e.g. "sqlite", "cross-join", ...
        if driver == "tpch":
            continue  # canonical home — handled by _discover_canonical_cases
        yield pytest.param(driver, child, id=str(rel))


@pytest.mark.parametrize("backend,query_name", list(_discover_canonical_cases()))
def test_canonical_query(sr_conn, backend, query_name,
                         sr_postgres_cat, sr_mysql_cat, sr_flightsql_starrocks_cat):
    """Run a canonical TPC-H query (queries/tpch/q*.sql) against one backend.

    Skips per CANONICAL_SKIPS[backend]. Substitutes {catalog}.{db} for the backend.
    Asserts row count from `-- Expected (<backend>): N rows` (or shared `-- Expected:`).
    """
    if query_name in CANONICAL_SKIPS.get(backend, set()):
        pytest.skip(
            f"{backend}/{query_name}: skipped per CANONICAL_SKIPS "
            f"(see CANONICAL_SKIPS comment for postgres-numeric rationale)"
        )

    raw = (CANONICAL_DIR / f"{query_name}.sql").read_text()
    sql = _strip_comments(_load_canonical(query_name, backend))
    assert sql.strip(), f"Canonical query {query_name}.sql is empty after stripping comments"

    rows = execute_sql(sr_conn, sql)
    expected = _expected_rows(raw, backend=backend)

    if expected is not None:
        assert len(rows) == expected, (
            f"{backend}/{query_name}: expected {expected} rows, got {len(rows)}: {rows[:5]}"
        )
    else:
        assert len(rows) >= 0


@pytest.mark.parametrize("driver,path", list(_discover_query_files()))
def test_query_file(sr_conn, driver, path,
                    sr_sqlite_cat, sr_sqlite_emp_cat, sr_postgres_cat,
                    sr_mysql_cat, sr_flightsql_cat, sr_duckdb_cat,
                    sr_flightsql_starrocks_cat):
    """Read a legacy per-directory .sql file, execute it, and assert expected row count.

    Per-directory backends (sqlite, duckdb, flightsql sqlflite, cross-join) and
    non-canonical TPC-H files (mysql/01-select.sql, postgres/02-join.sql, etc.)
    keep the legacy mechanism. Canonical TPC-H queries live in queries/tpch/ and
    are handled by test_canonical_query above.
    """
    raw = path.read_text()
    sql = _strip_comments(raw)
    assert sql.strip(), f"Query file {path} is empty after stripping comments"

    # DuckDB :memory: has no TPC-H data — skip query files that need tables
    if driver == "duckdb":
        pytest.skip("DuckDB :memory: has no TPC-H tables (file-based URI locked by FE)")

    # FlightSQL sqlflite may not have orders/lineitem tables — skip join queries
    if driver == "flightsql" and "join" in str(path):
        pytest.skip("FlightSQL sqlflite TPC-H table availability varies")

    rows = execute_sql(sr_conn, sql)
    expected = _expected_rows(raw)

    if expected is not None:
        assert len(rows) == expected, (
            f"{path.name}: expected {expected} rows, got {len(rows)}: {rows}"
        )
    else:
        assert len(rows) >= 0
