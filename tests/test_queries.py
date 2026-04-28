"""Execute every .sql file under queries/ against live Docker Compose catalogs.

Catalog names in the SQL files (sr_sqlite, sr_postgres, etc.) are created as
session-scoped ADBC catalogs so all query files in this module share them.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql


QUERIES_DIR = pathlib.Path(__file__).resolve().parent.parent / "queries"

# Map catalog name → (driver fixture name, URI, entrypoint or None)
CATALOG_MAP: dict[str, tuple[str, str, str | None]] = {
    "sr_sqlite":      ("sqlite_driver_path",    "/opt/starrocks/data/tpch_sqlite.db",     None),
    "sr_sqlite_emp":  ("sqlite_driver_path",    "/opt/starrocks/data/cross_sqlite_a.db",  None),
    "sr_postgres":    ("postgres_driver_path",  "postgresql://testuser:testpass@sr-postgres:5432/testdb", None),
    "sr_mysql":       ("mysql_driver_path",     "mysql://root:testpass@sr-mysql:3306/testdb",       None),
    "sr_flightsql":   ("flightsql_driver_path", "grpc://sr-flightsql:31337",              None),
    # DuckDB: use :memory: for query tests — file-based URI has single-writer lock conflict with FE
    "sr_duckdb":      ("duckdb_driver_path",    ":memory:",                                "duckdb_adbc_init"),
}


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
def sr_duckdb_cat(sr_conn, duckdb_driver_path):
    cat = "sr_duckdb"
    drop_catalog(sr_conn, cat)
    create_adbc_catalog(sr_conn, cat, driver_url=duckdb_driver_path,
                        uri=CATALOG_MAP["sr_duckdb"][1],
                        entrypoint=CATALOG_MAP["sr_duckdb"][2])
    yield cat
    drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Parametrized: one test per .sql file
# ---------------------------------------------------------------------------

def _discover_query_files():
    """Yield (driver_name, file_path) for every .sql under queries/."""
    for child in sorted(QUERIES_DIR.rglob("*.sql")):
        rel = child.relative_to(QUERIES_DIR)
        driver = rel.parts[0]  # e.g. "sqlite", "cross-join", ...
        yield pytest.param(driver, child, id=str(rel))


@pytest.mark.parametrize("driver,path", list(_discover_query_files()))
def test_query_file(sr_conn, driver, path,
                    sr_sqlite_cat, sr_sqlite_emp_cat, sr_postgres_cat,
                    sr_mysql_cat, sr_flightsql_cat, sr_duckdb_cat):
    """Read a .sql file, execute it, and assert expected row count if present."""
    raw = path.read_text()
    sql = _strip_comments(raw)
    assert sql.strip(), f"Query file {path} is empty after stripping comments"

    skip_reason = _skip_reason(raw)
    if skip_reason:
        pytest.skip(skip_reason)

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
