"""Cross-driver join tests -- D-10: federated queries across different ADBC backends.

Validates the core value proposition of ADBC external catalogs: a single StarRocks
query can JOIN data from two independently-loaded ADBC drivers (e.g., SQLite +
PostgreSQL, or two separate SQLite databases).
"""

from __future__ import annotations

import subprocess

import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql


# ---------------------------------------------------------------------------
# Module-level fixtures: seed backend databases with cross-join test data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cross_sqlite_db() -> str:
    """Create a SQLite database with an employees table for cross-join tests.

    Returns the absolute path to the database file.
    """
    db_path = "/tmp/sr_adbc_cross_sqlite.db"
    sql = (
        "CREATE TABLE IF NOT EXISTS employees"
        "(id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER);\n"
        "INSERT OR REPLACE INTO employees VALUES(1, 'Alice', 10);\n"
        "INSERT OR REPLACE INTO employees VALUES(2, 'Bob', 20);\n"
        "INSERT OR REPLACE INTO employees VALUES(3, 'Charlie', 10);\n"
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


@pytest.fixture(scope="module")
def cross_postgres_data(postgres_port):
    """Seed departments table into the PostgreSQL container for cross-join tests.

    Depends on ``postgres_port`` to ensure the container is running.
    """
    seed_sql = (
        "CREATE TABLE IF NOT EXISTS departments"
        "(dept_id INTEGER PRIMARY KEY, dept_name VARCHAR(50));"
        "INSERT INTO departments VALUES(10, 'Engineering') ON CONFLICT (dept_id) DO NOTHING;"
        "INSERT INTO departments VALUES(20, 'Marketing') ON CONFLICT (dept_id) DO NOTHING;"
        "INSERT INTO departments VALUES(30, 'Sales') ON CONFLICT (dept_id) DO NOTHING;"
    )
    result = subprocess.run(
        [
            "docker", "exec", "adbc_test_postgres",
            "psql", "-U", "testuser", "-d", "testdb", "-c", seed_sql,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to seed PostgreSQL departments data: {result.stderr}"
        )
    return True


# ---------------------------------------------------------------------------
# Test 1: SQLite-PostgreSQL cross-driver join (D-10)
# ---------------------------------------------------------------------------

@pytest.mark.cross_join
def test_sqlite_postgres_join(
    sr_conn,
    sqlite_driver_path,
    postgres_driver_path,
    postgres_port,
    cross_sqlite_db,
    cross_postgres_data,
):
    """JOIN employees (SQLite) with departments (PostgreSQL) through StarRocks.

    This is the core federation value test: a single SQL query joins data from
    two completely different ADBC drivers loaded by StarRocks.
    """
    sqlite_cat = "cross_sqlite_cat"
    pg_cat = "cross_pg_cat"
    try:
        # Create SQLite catalog pointing at employees table
        create_adbc_catalog(
            sr_conn,
            catalog_name=sqlite_cat,
            driver_url=sqlite_driver_path,
            uri=cross_sqlite_db,
        )

        # Create PostgreSQL catalog pointing at departments table
        create_adbc_catalog(
            sr_conn,
            catalog_name=pg_cat,
            driver_url=postgres_driver_path,
            uri="postgresql://testuser:testpass@127.0.0.1:5432/testdb",
        )

        # Cross-driver join using fully-qualified three-part names (Pitfall 8)
        # SQLite schema = "main", PostgreSQL schema = "public"
        rows = execute_sql(
            sr_conn,
            f"""
            SELECT e.name, d.dept_name
            FROM {sqlite_cat}.main.employees e
            JOIN {pg_cat}.public.departments d ON e.dept_id = d.dept_id
            ORDER BY e.name
            """,
        )

        # Expect at least 2 rows: Alice+Engineering, Bob+Marketing, Charlie+Engineering
        assert len(rows) >= 2, (
            f"Expected at least 2 joined rows, got {len(rows)}: {rows}"
        )

        # Verify specific join result -- Alice should be in Engineering (dept_id=10)
        row_names = [r[0] for r in rows]
        assert "Alice" in row_names, f"Expected 'Alice' in results, got {row_names}"

        # Check that Alice is paired with Engineering
        alice_rows = [r for r in rows if r[0] == "Alice"]
        assert alice_rows[0][1] == "Engineering", (
            f"Expected Alice in Engineering, got {alice_rows[0]}"
        )

    finally:
        drop_catalog(sr_conn, pg_cat)
        drop_catalog(sr_conn, sqlite_cat)


# ---------------------------------------------------------------------------
# Test 2: Two-SQLite cross-catalog join (D-10 variant, no Docker dependency)
# ---------------------------------------------------------------------------

@pytest.mark.cross_join
def test_two_sqlite_catalogs_join(sr_conn, sqlite_driver_path):
    """JOIN orders (SQLite A) with customers (SQLite B) through StarRocks.

    Simpler variant of D-10 that requires no Docker containers -- both backends
    are local SQLite files.
    """
    db_a = "/tmp/sr_adbc_cross_a.db"
    db_b = "/tmp/sr_adbc_cross_b.db"

    # Seed SQLite database A: orders table
    sql_a = (
        "CREATE TABLE IF NOT EXISTS orders"
        "(id INTEGER PRIMARY KEY, customer TEXT, amount REAL);\n"
        "INSERT OR REPLACE INTO orders VALUES(1, 'Alice', 100.0);\n"
        "INSERT OR REPLACE INTO orders VALUES(2, 'Bob', 200.0);\n"
    )
    subprocess.run(
        ["sqlite3", db_a], input=sql_a,
        capture_output=True, text=True, check=True,
    )

    # Seed SQLite database B: customers table
    sql_b = (
        "CREATE TABLE IF NOT EXISTS customers"
        "(name TEXT PRIMARY KEY, city TEXT);\n"
        "INSERT OR REPLACE INTO customers VALUES('Alice', 'NYC');\n"
        "INSERT OR REPLACE INTO customers VALUES('Bob', 'SF');\n"
    )
    subprocess.run(
        ["sqlite3", db_b], input=sql_b,
        capture_output=True, text=True, check=True,
    )

    cat_a = "cross_a_cat"
    cat_b = "cross_b_cat"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat_a,
            driver_url=sqlite_driver_path,
            uri=db_a,
        )
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat_b,
            driver_url=sqlite_driver_path,
            uri=db_b,
        )

        # Cross-catalog join using fully-qualified three-part names
        rows = execute_sql(
            sr_conn,
            f"""
            SELECT o.customer, o.amount, c.city
            FROM {cat_a}.main.orders o
            JOIN {cat_b}.main.customers c ON o.customer = c.name
            ORDER BY o.customer
            """,
        )

        # Expect exactly 2 rows: Alice/100.0/NYC and Bob/200.0/SF
        assert len(rows) == 2, f"Expected 2 joined rows, got {len(rows)}: {rows}"

        # Row 0: Alice, 100.0, NYC
        assert rows[0][0] == "Alice", f"Expected 'Alice', got {rows[0][0]}"
        assert abs(float(rows[0][1]) - 100.0) < 0.01, (
            f"Expected amount ~100.0, got {rows[0][1]}"
        )
        assert rows[0][2] == "NYC", f"Expected 'NYC', got {rows[0][2]}"

        # Row 1: Bob, 200.0, SF
        assert rows[1][0] == "Bob", f"Expected 'Bob', got {rows[1][0]}"
        assert abs(float(rows[1][1]) - 200.0) < 0.01, (
            f"Expected amount ~200.0, got {rows[1][1]}"
        )
        assert rows[1][2] == "SF", f"Expected 'SF', got {rows[1][2]}"

    finally:
        drop_catalog(sr_conn, cat_b)
        drop_catalog(sr_conn, cat_a)
