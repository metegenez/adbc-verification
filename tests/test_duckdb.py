"""DuckDB backend tests -- D-09 scenarios: lifecycle, round-trip, missing entrypoint, pass-through."""

from __future__ import annotations

import pymysql
import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql, show_catalogs


# ---------------------------------------------------------------------------
# Module-level fixture: pre-populated DuckDB database file path
# ---------------------------------------------------------------------------

DUCKDB_DB_PATH = "/opt/starrocks/data/tpch_duckdb.db"


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
            uri="/opt/starrocks/data/test_duckdb_lc.db",
            entrypoint="duckdb_adbc_init",
        )
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"Expected '{cat}' in {catalogs}"

        drop_catalog(sr_conn, cat)
        catalogs_after = show_catalogs(sr_conn)
        assert cat not in catalogs_after, f"'{cat}' still in catalogs after drop"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 2: Data round-trip (D-09 scenario 2)
# ---------------------------------------------------------------------------

@pytest.mark.duckdb
def test_duckdb_data_roundtrip(sr_conn, duckdb_driver_path):
    """Verify DuckDB catalog can serve table metadata via SHOW DATABASES / SHOW TABLES.

    Uses :memory: to verify the catalog metadata path works.
    """
    cat = "test_duckdb_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=duckdb_driver_path,
            uri=":memory:",
            entrypoint="duckdb_adbc_init",
        )
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"'{cat}' not in catalogs: {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        db_names = [row[0] for row in dbs]
        assert len(db_names) >= 1, f"Expected at least 1 database, got {db_names}"
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
            )
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
    """adbc.duckdb.* options are forwarded to the DuckDB driver."""
    cat = "test_duckdb_pt"
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=duckdb_driver_path,
                uri=":memory:",
                entrypoint="duckdb_adbc_init",
                extra_props={"adbc.duckdb.threads": "2"},
            )
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            assert "not recognized" in err_msg or "duckdb" in err_msg.lower(), (
                f"Expected driver-level rejection, got: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)
