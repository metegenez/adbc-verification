"""SQLite backend tests -- D-09 scenarios: lifecycle, round-trip, tables, negative, pass-through."""

from __future__ import annotations

import pymysql
import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql, show_catalogs


# ---------------------------------------------------------------------------
# Module-level fixture: pre-populated SQLite database file path
# ---------------------------------------------------------------------------

TEST_DB_PATH = "/opt/starrocks/data/test_sqlite.db"


@pytest.fixture(scope="module")
def sqlite_test_db() -> str:
    """Return the path to the pre-baked SQLite test database in the container."""
    return TEST_DB_PATH


# ---------------------------------------------------------------------------
# Test 1: Catalog lifecycle (D-09 scenario 1)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_catalog_lifecycle(sr_conn, sqlite_driver_path):
    """CREATE CATALOG -> SHOW CATALOGS -> SHOW DATABASES -> DROP CATALOG."""
    cat = "test_sqlite_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=sqlite_driver_path,
            uri="/opt/starrocks/data/test_sqlite_lc.db",
        )
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Expected '{cat}' in {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {len(dbs)}"

        drop_catalog(sr_conn, cat)
        catalogs_after = show_catalogs(sr_conn)
        assert cat not in catalogs_after, f"'{cat}' still in catalogs after drop"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 2: Data round-trip (D-09 scenario 2)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_data_roundtrip(sr_conn, sqlite_driver_path, sqlite_test_db):
    """SELECT rows from pre-baked SQLite file through StarRocks ADBC catalog."""
    cat = "test_sqlite_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=sqlite_driver_path,
            uri=sqlite_test_db,
        )
        rows = execute_sql(
            sr_conn,
            f"SELECT * FROM {cat}.main.test_data ORDER BY id",
        )
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"

        assert rows[0][0] == 1
        assert rows[0][1] == "alice"
        assert abs(float(rows[0][2]) - 10.5) < 0.01
        assert rows[2][1] == "charlie"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 3: SHOW TABLES (D-09 scenario 1 extended)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_show_tables(sr_conn, sqlite_driver_path, sqlite_test_db):
    """SHOW TABLES lists the test_data table from the pre-baked database."""
    cat = "test_sqlite_st"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=sqlite_driver_path,
            uri=sqlite_test_db,
        )
        tables_result = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.main")
        table_names = [row[0] for row in tables_result]
        assert "test_data" in table_names, (
            f"Expected 'test_data' in tables, got {table_names}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 4: Bad driver_url (D-09 scenario 3, VAL-03)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_bad_driver_url(sr_conn):
    """Creating a catalog with a nonexistent driver .so must raise an error."""
    cat = "test_sqlite_bad_drv"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.ProgrammingError, pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url="/nonexistent/path/libfake.so",
                uri=":memory:",
            )
        err_msg = str(exc_info.value)
        assert "/nonexistent/path/libfake.so" in err_msg or "libfake" in err_msg, (
            f"Error message should reference the bad driver path, got: {err_msg}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 5: Unknown top-level key (D-09 scenario 3, VAL-04)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_unknown_top_level_key(sr_conn, sqlite_driver_path):
    """Unknown catalog property key must be rejected with a clear error naming the key."""
    cat = "test_sqlite_bad_key"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                extra_props={"bogus_key": "bogus_val"},
            )
        err_msg = str(exc_info.value)
        assert "bogus_key" in err_msg, (
            f"Error message should contain 'bogus_key', got: {err_msg}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 6: adbc.* pass-through (D-09 scenario 4)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_adbc_passthrough(sr_conn, sqlite_driver_path):
    """adbc.* options are forwarded to the driver (not rejected by StarRocks validation)."""
    cat = "test_sqlite_pt"
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                uri=":memory:",
                extra_props={"adbc.sqlite.load_extension.enabled": "false"},
            )
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            assert "Unknown database option" in err_msg or "SQLite" in err_msg, (
                f"Expected driver-level rejection, got StarRocks validation error: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)
