"""MySQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data round-trip, show tables, negative, pass-
through).  Uses a ``mysql:8.0`` Docker container as the backend.  Test data is
seeded via ``docker exec mysql`` into the container.

This module validates that the ADBC MySQL driver (from ADBC Driver Foundry)
works end-to-end through StarRocks, including correct backtick identifier
quoting detected via ``_sr_identifier_quote``.
"""

from __future__ import annotations

import subprocess

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)

# ---------------------------------------------------------------------------
# MySQL connection constants
# ---------------------------------------------------------------------------

MYSQL_USER = "root"
MYSQL_PASS = "testpass"
MYSQL_DB = "testdb"
MYSQL_CONTAINER = "adbc_test_mysql"
_MYSQL_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASS}@127.0.0.1:3306/{MYSQL_DB}"

# ---------------------------------------------------------------------------
# Module-level fixture: seed test data into MySQL container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mysql_test_data(mysql_port):
    """Seed test_data table into the MySQL container."""
    seed_sql = (
        "CREATE TABLE IF NOT EXISTS test_data"
        "(id INT PRIMARY KEY, name VARCHAR(50), value DOUBLE);"
        "INSERT IGNORE INTO test_data VALUES(1, 'alice', 10.5);"
        "INSERT IGNORE INTO test_data VALUES(2, 'bob', 20.3);"
        "INSERT IGNORE INTO test_data VALUES(3, 'charlie', 30.1);"
    )
    # Retry seeding — MySQL may still be initializing even after port opens
    import time
    for attempt in range(5):
        result = subprocess.run(
            [
                "docker", "exec", MYSQL_CONTAINER,
                "mysql", f"-u{MYSQL_USER}", f"-p{MYSQL_PASS}", MYSQL_DB,
                "-e", seed_sql,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            break
        time.sleep(3)
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to seed MySQL test data after 5 attempts: {result.stderr}"
        )
    return True


# ---------------------------------------------------------------------------
# D-09 Scenario 1: Catalog lifecycle
# ---------------------------------------------------------------------------

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

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        db_names = [row[0] for row in dbs]
        assert len(db_names) >= 1, f"Expected at least 1 database, got {db_names}"

        drop_catalog(sr_conn, cat)
        catalogs_after = show_catalogs(sr_conn)
        assert cat not in catalogs_after, f"'{cat}' still in catalogs after drop"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 2: Data round-trip
# ---------------------------------------------------------------------------

@pytest.mark.mysql
def test_mysql_data_roundtrip(sr_conn, mysql_driver_path, mysql_port, mysql_test_data):
    """Insert rows into MySQL, SELECT through StarRocks ADBC catalog."""
    cat = "test_mysql_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=mysql_driver_path,
            uri=_MYSQL_URI,
        )
        rows = execute_sql(
            sr_conn,
            f"SELECT * FROM {cat}.{MYSQL_DB}.test_data ORDER BY id",
        )
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
        assert rows[0][0] == 1
        assert rows[0][1] == "alice"
        assert abs(float(rows[0][2]) - 10.5) < 0.01
        assert rows[2][0] == 3
        assert rows[2][1] == "charlie"
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 1 extended: SHOW TABLES
# ---------------------------------------------------------------------------

@pytest.mark.mysql
def test_mysql_show_tables(sr_conn, mysql_driver_path, mysql_port, mysql_test_data):
    """SHOW TABLES lists the test_data table."""
    cat = "test_mysql_st"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=mysql_driver_path,
            uri=_MYSQL_URI,
        )
        tables_result = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.{MYSQL_DB}")
        table_names = [row[0] for row in tables_result]
        assert "test_data" in table_names, (
            f"Expected 'test_data' in tables, got {table_names}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 3: Bad URI (negative)
# ---------------------------------------------------------------------------

@pytest.mark.mysql
def test_mysql_bad_uri(sr_conn, mysql_driver_path):
    """A bad MySQL URI must raise an error at catalog creation."""
    cat = "test_mysql_bad"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.ProgrammingError, pymysql.err.DatabaseError)
        ):
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=mysql_driver_path,
                uri="mysql://baduser:badpass@127.0.0.1:59999/nodb",
            )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Cross-driver: MySQL + SQLite join
# ---------------------------------------------------------------------------

@pytest.mark.mysql
@pytest.mark.cross_join
def test_mysql_sqlite_join(
    sr_conn, mysql_driver_path, sqlite_driver_path, mysql_port, mysql_test_data
):
    """JOIN MySQL test_data with a SQLite orders table through StarRocks."""
    import subprocess as sp

    # Seed SQLite with orders
    sqlite_db = "/tmp/sr_adbc_mysql_cross.db"
    sp.run(
        ["sqlite3", sqlite_db],
        input=(
            "CREATE TABLE IF NOT EXISTS orders"
            "(id INTEGER PRIMARY KEY, customer TEXT, amount REAL);\n"
            "INSERT OR REPLACE INTO orders VALUES(1, 'alice', 500.0);\n"
            "INSERT OR REPLACE INTO orders VALUES(2, 'bob', 300.0);\n"
        ),
        capture_output=True,
        text=True,
        check=True,
    )

    mysql_cat = "cross_mysql_cat"
    sqlite_cat = "cross_sqlite_mysql_cat"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=mysql_cat,
            driver_url=mysql_driver_path,
            uri=_MYSQL_URI,
        )
        create_adbc_catalog(
            sr_conn,
            catalog_name=sqlite_cat,
            driver_url=sqlite_driver_path,
            uri=sqlite_db,
        )

        rows = execute_sql(
            sr_conn,
            f"""
            SELECT m.name, m.value, o.amount
            FROM {mysql_cat}.{MYSQL_DB}.test_data m
            JOIN {sqlite_cat}.main.orders o ON m.name = o.customer
            ORDER BY m.name
            """,
        )
        assert len(rows) == 2, f"Expected 2 joined rows, got {len(rows)}: {rows}"
        assert rows[0][0] == "alice"
        assert rows[1][0] == "bob"
    finally:
        drop_catalog(sr_conn, sqlite_cat)
        drop_catalog(sr_conn, mysql_cat)
