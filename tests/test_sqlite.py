"""SQLite backend tests -- D-09 scenarios: lifecycle, round-trip, tables, negative, pass-through."""

from __future__ import annotations

import subprocess
import tempfile

import pymysql
import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql, show_catalogs


# ---------------------------------------------------------------------------
# Module-level fixture: pre-populate a SQLite database file with test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sqlite_test_db() -> str:
    """Create a SQLite database at /tmp/sr_adbc_test_sqlite.db with test rows.

    Returns the absolute path to the database file.
    """
    db_path = "/tmp/sr_adbc_test_sqlite.db"
    sql = (
        "CREATE TABLE IF NOT EXISTS test_data"
        "(id INTEGER PRIMARY KEY, name TEXT, value REAL);\n"
        "INSERT OR REPLACE INTO test_data VALUES(1, 'alice', 10.5);\n"
        "INSERT OR REPLACE INTO test_data VALUES(2, 'bob', 20.3);\n"
        "INSERT OR REPLACE INTO test_data VALUES(3, 'charlie', 30.1);\n"
    )
    result = subprocess.run(
        ["sqlite3", db_path],
        input=sql,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.returncode == 0, f"sqlite3 setup failed: {result.stderr}"
    return db_path


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
            uri="/tmp/sr_adbc_test_sqlite_lc.db",
        )
        # Catalog must appear in SHOW CATALOGS
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Expected '{cat}' in {catalogs}"

        # SHOW DATABASES must return at least one result (SQLite always has 'main')
        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {len(dbs)}"

        # Drop and verify removal
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
    """Insert rows into SQLite file, SELECT through StarRocks ADBC catalog."""
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

        # First row: id=1, name='alice', value~10.5
        assert rows[0][0] == 1
        assert rows[0][1] == "alice"
        assert abs(float(rows[0][2]) - 10.5) < 0.01

        # Third row: id=3, name='charlie'
        assert rows[2][0] == 3
        assert rows[2][1] == "charlie"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 3: SHOW TABLES (D-09 scenario 1 extended)
# ---------------------------------------------------------------------------

@pytest.mark.sqlite
def test_sqlite_show_tables(sr_conn, sqlite_driver_path, sqlite_test_db):
    """SHOW TABLES lists the test_data table created by the fixture."""
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
        # Error should reference the bad path (VAL-03)
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
        # VAL-04: error message must name the unknown key
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
    """adbc.* options are forwarded to the driver (not rejected by StarRocks validation).

    The driver itself may reject unknown adbc.* options — that's fine. The test
    verifies that StarRocks forwards the option (error comes from the driver,
    not from StarRocks property validation).
    """
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
            # Option accepted by driver — pass-through confirmed
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            # If error comes from the driver (contains driver-specific text),
            # that proves StarRocks forwarded the option — pass-through works
            assert "Unknown database option" in err_msg or "SQLite" in err_msg, (
                f"Expected driver-level rejection, got StarRocks validation error: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)
