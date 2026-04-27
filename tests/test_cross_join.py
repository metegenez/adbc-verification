"""Cross-driver join tests -- D-10: federated queries across different ADBC backends.

Uses pre-baked SQLite databases from the StarRocks container image and
PostgreSQL data pre-loaded via init scripts.
"""

from __future__ import annotations

import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql


# ---------------------------------------------------------------------------
# Module-level fixtures: paths to pre-baked data files in the container
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cross_sqlite_db() -> str:
    """Return path to pre-baked SQLite employees database in the container."""
    return "/opt/starrocks/data/cross_sqlite_a.db"


@pytest.fixture(scope="module")
def cross_postgres_data(postgres_port):
    """Data is pre-loaded by PostgreSQL init scripts. This fixture is a pass-through."""
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
    """JOIN employees (SQLite) with departments (PostgreSQL) through StarRocks."""
    sqlite_cat = "cross_sqlite_cat"
    pg_cat = "cross_pg_cat"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=sqlite_cat,
            driver_url=sqlite_driver_path,
            uri=cross_sqlite_db,
        )

        create_adbc_catalog(
            sr_conn,
            catalog_name=pg_cat,
            driver_url=postgres_driver_path,
            uri="postgresql://testuser:testpass@sr-postgres:5432/testdb",
        )

        rows = execute_sql(
            sr_conn,
            f"""
            SELECT e.customer, d.dept_name
            FROM {sqlite_cat}.main.orders e
            JOIN {pg_cat}.public.departments d
              ON CASE
                WHEN e.customer = 'Alice' THEN 10
                WHEN e.customer = 'Bob' THEN 20
              END = d.dept_id
            ORDER BY e.customer
            """,
        )

        assert len(rows) >= 2, (
            f"Expected at least 2 joined rows, got {len(rows)}: {rows}"
        )

        row_names = [r[0] for r in rows]
        assert "Alice" in row_names, f"Expected 'Alice' in results, got {row_names}"

    finally:
        drop_catalog(sr_conn, pg_cat)
        drop_catalog(sr_conn, sqlite_cat)


# ---------------------------------------------------------------------------
# Test 2: Two-SQLite cross-catalog join (D-10 variant, no Docker dependency)
# ---------------------------------------------------------------------------

@pytest.mark.cross_join
def test_two_sqlite_catalogs_join(sr_conn, sqlite_driver_path):
    """JOIN orders (SQLite A) with customers (SQLite B) through StarRocks.

    Uses pre-baked cross_sqlite_a.db (orders) and cross_sqlite_b.db (customers).
    """
    cat_a = "cross_a_cat"
    cat_b = "cross_b_cat"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat_a,
            driver_url=sqlite_driver_path,
            uri="/opt/starrocks/data/cross_sqlite_a.db",
        )
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat_b,
            driver_url=sqlite_driver_path,
            uri="/opt/starrocks/data/cross_sqlite_b.db",
        )

        rows = execute_sql(
            sr_conn,
            f"""
            SELECT o.customer, o.amount, c.city
            FROM {cat_a}.main.orders o
            JOIN {cat_b}.main.customers c ON o.customer = c.name
            ORDER BY o.customer
            """,
        )

        assert len(rows) == 2, f"Expected 2 joined rows, got {len(rows)}: {rows}"
        assert rows[0][0] == "Alice", f"Expected 'Alice', got {rows[0][0]}"
        assert abs(float(rows[0][1]) - 100.0) < 0.01
        assert rows[0][2] == "NYC", f"Expected 'NYC', got {rows[0][2]}"
        assert rows[1][0] == "Bob", f"Expected 'Bob', got {rows[1][0]}"
        assert abs(float(rows[1][1]) - 200.0) < 0.01
        assert rows[1][2] == "SF", f"Expected 'SF', got {rows[1][2]}"

    finally:
        drop_catalog(sr_conn, cat_b)
        drop_catalog(sr_conn, cat_a)
