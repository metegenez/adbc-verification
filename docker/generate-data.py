#!/usr/bin/env python3
"""Pre-bake SQLite and DuckDB database files for Docker Compose verification suite.

Generated files go into docker/data/, copied into the StarRocks image at
/opt/starrocks/data/ by the Dockerfile.

Usage:  cd docker && python generate-data.py
"""
import os
import sqlite3
import sys


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def create_sqlite_db(db_path: str, statements: list[str]) -> None:
    """Create a SQLite database file from a list of SQL statements."""
    conn = sqlite3.connect(db_path)
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    data_dir = os.path.join(os.path.dirname(__file__) or ".", "data")
    ensure_dir(data_dir)

    # 1. test_sqlite.db — simple test data for lifecycle tests
    create_sqlite_db(
        os.path.join(data_dir, "test_sqlite.db"),
        [
            "CREATE TABLE IF NOT EXISTS test_data"
            "(id INTEGER PRIMARY KEY, name TEXT, value REAL)",
            "INSERT OR REPLACE INTO test_data VALUES(1, 'alice', 10.5)",
            "INSERT OR REPLACE INTO test_data VALUES(2, 'bob', 20.3)",
            "INSERT OR REPLACE INTO test_data VALUES(3, 'charlie', 30.1)",
        ],
    )
    print("  test_sqlite.db — created (1 table, 3 rows)")

    # 2. cross_sqlite_a.db — orders table for cross-join tests
    create_sqlite_db(
        os.path.join(data_dir, "cross_sqlite_a.db"),
        [
            "CREATE TABLE IF NOT EXISTS orders"
            "(id INTEGER PRIMARY KEY, customer TEXT, amount REAL)",
            "INSERT OR REPLACE INTO orders VALUES(1, 'Alice', 100.0)",
            "INSERT OR REPLACE INTO orders VALUES(2, 'Bob', 200.0)",
        ],
    )
    print("  cross_sqlite_a.db — created (orders table, 2 rows)")

    # 3. cross_sqlite_b.db — customers table for cross-join tests
    create_sqlite_db(
        os.path.join(data_dir, "cross_sqlite_b.db"),
        [
            "CREATE TABLE IF NOT EXISTS customers"
            "(name TEXT PRIMARY KEY, city TEXT)",
            "INSERT OR REPLACE INTO customers VALUES('Alice', 'NYC')",
            "INSERT OR REPLACE INTO customers VALUES('Bob', 'SF')",
        ],
    )
    print("  cross_sqlite_b.db — created (customers table, 2 rows)")

    # 4. tpch_duckdb.db — TPC-H seed data via duckdb package
    tpch_path = os.path.join(data_dir, "tpch_duckdb.db")
    try:
        import duckdb as _duckdb
    except ImportError:
        print("  tpch_duckdb.db — SKIPPED (duckdb package not available)")
        return 0

    if os.path.exists(tpch_path):
        os.remove(tpch_path)

    conn = _duckdb.connect(tpch_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS region"
            "(r_regionkey INTEGER PRIMARY KEY, r_name VARCHAR, r_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nation"
            "(n_nationkey INTEGER PRIMARY KEY, n_name VARCHAR, n_regionkey INTEGER, n_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS orders"
            "(o_orderkey INTEGER PRIMARY KEY, o_custkey INTEGER, o_orderstatus VARCHAR,"
            " o_totalprice DOUBLE, o_orderdate DATE, o_orderpriority VARCHAR,"
            " o_clerk VARCHAR, o_shippriority INTEGER, o_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lineitem"
            "(l_orderkey INTEGER, l_partkey INTEGER, l_suppkey INTEGER, l_linenumber INTEGER,"
            " l_quantity DOUBLE, l_extendedprice DOUBLE, l_discount DOUBLE, l_tax DOUBLE,"
            " l_returnflag VARCHAR, l_linestatus VARCHAR, l_shipdate DATE,"
            " l_commitdate DATE, l_receiptdate DATE, l_shipinstruct VARCHAR,"
            " l_shipmode VARCHAR, l_comment VARCHAR, PRIMARY KEY (l_orderkey, l_linenumber))"
        )
        conn.execute(
            "INSERT INTO region VALUES"
            "(0, 'AFRICA', 'lar deposits.'),"
            "(1, 'AMERICA', 'hs use ironic.'),"
            "(2, 'ASIA', 'ges. thinly even.'),"
            "(3, 'EUROPE', 'ly final courts.'),"
            "(4, 'MIDDLE EAST', 'uickly special accounts.')"
        )
        conn.execute(
            "INSERT INTO nation VALUES"
            "(0, 'ALGERIA', 0, 'furiously regular'),"
            "(1, 'ARGENTINA', 1, 'al foxes promise'),"
            "(2, 'BRAZIL', 1, 'y alongside'),"
            "(3, 'CANADA', 1, 'eas hang ironic'),"
            "(4, 'EGYPT', 4, 'y above the'),"
            "(5, 'ETHIOPIA', 0, 'ven packages'),"
            "(6, 'FRANCE', 3, 'refully final'),"
            "(7, 'GERMANY', 3, 'l platelets.'),"
            "(8, 'INDIA', 2, 'ss excuses'),"
            "(9, 'INDONESIA', 2, 'slyly express'),"
            "(10, 'IRAN', 4, 'efully alongside'),"
            "(11, 'IRAQ', 4, 'nic deposits'),"
            "(12, 'JAPAN', 2, 'ously. final'),"
            "(13, 'JORDAN', 4, 'ic deposits'),"
            "(14, 'KENYA', 0, 'pending excuses'),"
            "(15, 'MOROCCO', 0, 'rns. blithely'),"
            "(16, 'MOZAMBIQUE', 0, 's. ironic'),"
            "(17, 'PERU', 1, 'platelets.'),"
            "(18, 'CHINA', 2, 'c dependencies.'),"
            "(19, 'ROMANIA', 3, 'ular asymptotes'),"
            "(20, 'SAUDI ARABIA', 4, 'ts. silent'),"
            "(21, 'VIETNAM', 2, 'hely enticingly'),"
            "(22, 'RUSSIA', 3, 'requests against'),"
            "(23, 'UNITED KINGDOM', 3, 'eans boost'),"
            "(24, 'UNITED STATES', 1, 'y final packages.')"
        )
        conn.execute(
            "INSERT INTO orders VALUES"
            "(1, 370, 'O', 172799.49, '1996-01-02', '5-LOW', 'Clerk#000000951', 0, 'nstructions sleep'),"
            "(2, 781, 'O', 38426.09, '1996-12-01', '1-URGENT', 'Clerk#000000880', 0, 'foxes. pending'),"
            "(3, 1234, 'F', 205654.30, '1993-10-14', '5-LOW', 'Clerk#000000955', 0, 'sly final'),"
            "(4, 1369, 'O', 56000.91, '1995-10-11', '5-LOW', 'Clerk#000000124', 0, 'sits. slyly'),"
            "(5, 445, 'F', 105367.67, '1994-07-30', '5-LOW', 'Clerk#000000925', 0, 'quickly. bold')"
        )
        conn.execute(
            "INSERT INTO lineitem VALUES"
            "(1, 1552, 93, 1, 17.00, 24710.35, 0.04, 0.02, 'N', 'O', '1996-03-13', '1996-02-12', '1996-03-22', 'DELIVER IN PERSON', 'TRUCK', 'egular courts'),"
            "(1, 674, 75, 2, 36.00, 56688.12, 0.09, 0.06, 'N', 'O', '1996-04-12', '1996-02-28', '1996-04-20', 'TAKE BACK RETURN', 'MAIL', 'ly final'),"
            "(2, 1061, 62, 1, 38.00, 37402.28, 0.00, 0.05, 'N', 'O', '1997-01-28', '1997-01-14', '1997-02-02', 'TAKE BACK RETURN', 'RAIL', 'ven requests'),"
            "(3, 420, 21, 1, 45.00, 54270.90, 0.06, 0.00, 'R', 'F', '1994-02-02', '1994-01-04', '1994-02-23', 'NONE', 'AIR', 'ongside of'),"
            "(4, 880, 81, 1, 30.00, 53850.40, 0.03, 0.08, 'N', 'O', '1996-01-10', '1995-12-14', '1996-01-18', 'DELIVER IN PERSON', 'REG AIR', 'sly final')"
        )
    finally:
        conn.close()
    print(f"  tpch_duckdb.db — created (4 tables, TPC-H seed data)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
