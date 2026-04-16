"""DuckDB backend tests -- D-09 scenarios: lifecycle, round-trip, missing entrypoint, pass-through."""

from __future__ import annotations

import os

import pymysql
import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql, show_catalogs


# ---------------------------------------------------------------------------
# Module-level fixture: pre-populate a DuckDB database file with test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def duckdb_test_db() -> str:
    """Create a DuckDB database at /tmp/sr_adbc_test_duckdb.db with test rows.

    Uses the duckdb Python package (installed in .venv).  If not available,
    the test is skipped.

    Returns the absolute path to the database file.
    """
    try:
        import duckdb as _duckdb
    except ImportError:
        pytest.skip("duckdb Python package not available for data setup")

    db_path = "/tmp/sr_adbc_test_duckdb.db"

    # Remove stale file to get a clean state
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = _duckdb.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test_data"
            "(id INTEGER, name VARCHAR, value DOUBLE)"
        )
        conn.execute(
            "INSERT INTO test_data VALUES"
            "(1, 'alice', 10.5),"
            "(2, 'bob', 20.3),"
            "(3, 'charlie', 30.1)"
        )
    finally:
        conn.close()

    return db_path


# ---------------------------------------------------------------------------
# Test 1: Catalog lifecycle (D-09 scenario 1)
# ---------------------------------------------------------------------------

@pytest.mark.duckdb
def test_duckdb_catalog_lifecycle(sr_conn, duckdb_driver_path):
    """CREATE CATALOG -> SHOW CATALOGS -> DROP CATALOG with duckdb_adbc_init entrypoint."""
    cat = "test_duckdb_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=duckdb_driver_path,
            uri="/tmp/sr_adbc_test_duckdb_lc.db",
            entrypoint="duckdb_adbc_init",
        )
        # Catalog must appear in SHOW CATALOGS
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Expected '{cat}' in {catalogs}"

        # Drop and verify removal
        drop_catalog(sr_conn, cat)
        catalogs_after = show_catalogs(sr_conn)
        assert cat not in catalogs_after, f"'{cat}' still in catalogs after drop"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 2: Data round-trip (D-09 scenario 2)
# ---------------------------------------------------------------------------

@pytest.mark.duckdb
def test_duckdb_data_roundtrip(sr_conn, duckdb_driver_path, duckdb_test_db):
    """Insert rows into DuckDB file, SELECT through StarRocks ADBC catalog."""
    cat = "test_duckdb_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=duckdb_driver_path,
            uri=duckdb_test_db,
            entrypoint="duckdb_adbc_init",
        )
        rows = execute_sql(
            sr_conn,
            f"SELECT * FROM {cat}.main.test_data ORDER BY id",
        )
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"

        # First row: id=1, name='alice'
        assert rows[0][0] == 1
        assert rows[0][1] == "alice"

        # Third row: id=3, name='charlie'
        assert rows[2][0] == 3
        assert rows[2][1] == "charlie"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 3: Missing entrypoint (D-09 scenario 3, PROP-03 / Pitfall 5)
# ---------------------------------------------------------------------------

@pytest.mark.duckdb
def test_duckdb_missing_entrypoint(sr_conn, duckdb_driver_path):
    """Omitting driver_entrypoint for DuckDB must fail -- AdbcDriverInit symbol does not exist."""
    cat = "test_duckdb_no_ep"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=duckdb_driver_path,
                uri=":memory:",
                # Deliberately omit entrypoint -- DuckDB does not export AdbcDriverInit
            )
        # Error should reference the entrypoint/symbol issue (VAL-03)
        err_msg = str(exc_info.value).lower()
        assert (
            "entrypoint" in err_msg
            or "symbol" in err_msg
            or "init" in err_msg
            or "dlsym" in err_msg
        ), f"Error message should reference entrypoint/symbol issue, got: {err_msg}"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 4: adbc.* pass-through (D-09 scenario 4)
# ---------------------------------------------------------------------------

@pytest.mark.duckdb
def test_duckdb_adbc_passthrough(sr_conn, duckdb_driver_path):
    """adbc.duckdb.* options are forwarded to the DuckDB driver without error."""
    cat = "test_duckdb_pt"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=duckdb_driver_path,
            uri=":memory:",
            entrypoint="duckdb_adbc_init",
            extra_props={"adbc.duckdb.threads": "2"},
        )
        # If we got here, the adbc.* option was accepted and forwarded
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Catalog '{cat}' should exist after creation"
    finally:
        drop_catalog(sr_conn, cat)
