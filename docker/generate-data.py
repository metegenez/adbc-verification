#!/usr/bin/env python3
"""Pre-bake SQLite and DuckDB database files for Docker Compose verification suite.

Generated files go into docker/data/, copied into the StarRocks image at
/opt/starrocks/data/ by the Dockerfile.

Usage:  cd docker && python generate-data.py
"""
import os
import sqlite3
import sys


DATA_DIR = os.path.join(os.path.dirname(__file__) or ".", "data")


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def create_test_sqlite() -> None:
    """Create test_sqlite.db with simple test_data table."""
    path = os.path.join(DATA_DIR, "test_sqlite.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS test_data"
            "(id INTEGER PRIMARY KEY, name TEXT, value REAL)"
        )
        conn.execute("INSERT OR REPLACE INTO test_data VALUES(1, 'alice', 10.5)")
        conn.execute("INSERT OR REPLACE INTO test_data VALUES(2, 'bob', 20.3)")
        conn.execute("INSERT OR REPLACE INTO test_data VALUES(3, 'charlie', 30.1)")
        conn.commit()
    finally:
        conn.close()
    print("  test_sqlite.db — created (1 table, 3 rows)")


def create_cross_sqlite_a() -> None:
    """Create cross_sqlite_a.db with employees table for cross-join tests."""
    path = os.path.join(DATA_DIR, "cross_sqlite_a.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS employees"
            "(id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER)"
        )
        conn.execute("INSERT OR REPLACE INTO employees VALUES(1, 'Alice', 10)")
        conn.execute("INSERT OR REPLACE INTO employees VALUES(2, 'Bob', 20)")
        conn.execute("INSERT OR REPLACE INTO employees VALUES(3, 'Charlie', 10)")
        conn.commit()
    finally:
        conn.close()
    print("  cross_sqlite_a.db — created (employees table, 3 rows)")


def create_cross_sqlite_b() -> None:
    """Create cross_sqlite_b.db with customers table for cross-join tests."""
    path = os.path.join(DATA_DIR, "cross_sqlite_b.db")
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS customers"
            "(name TEXT PRIMARY KEY, city TEXT)"
        )
        conn.execute("INSERT OR REPLACE INTO customers VALUES('Alice', 'NYC')")
        conn.execute("INSERT OR REPLACE INTO customers VALUES('Bob', 'SF')")
        conn.commit()
    finally:
        conn.close()
    print("  cross_sqlite_b.db — created (customers table, 2 rows)")


def create_tpch_sqlite() -> None:
    """Create tpch_sqlite.db with full TPC-H schema (8 tables) and seed data."""
    path = os.path.join(DATA_DIR, "tpch_sqlite.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            _read_init_sql(os.path.join("init", "sqlflite", "init.sql"))
        )
    finally:
        conn.close()
    print("  tpch_sqlite.db — created (8 TPC-H tables)")


def create_tpch_sqlflite() -> None:
    """Create tpch_sqlflite.db — identical content to tpch_sqlite.db."""
    path = os.path.join(DATA_DIR, "tpch_sqlflite.db")
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            _read_init_sql(os.path.join("init", "sqlflite", "init.sql"))
        )
    finally:
        conn.close()
    print("  tpch_sqlflite.db — created (8 TPC-H tables)")


def create_tpch_duckdb() -> None:
    """Create tpch_duckdb.db with full TPC-H schema and seed data using duckdb."""
    path = os.path.join(DATA_DIR, "tpch_duckdb.db")
    try:
        import duckdb as _duckdb
    except ImportError:
        print("  tpch_duckdb.db — SKIPPED (duckdb package not available)")
        return

    if os.path.exists(path):
        os.remove(path)

    conn = _duckdb.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS part ("
            "p_partkey INTEGER PRIMARY KEY, p_name VARCHAR, p_mfgr VARCHAR,"
            "p_brand VARCHAR, p_type VARCHAR, p_size INTEGER, p_container VARCHAR,"
            "p_retailprice DOUBLE, p_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS supplier ("
            "s_suppkey INTEGER PRIMARY KEY, s_name VARCHAR, s_address VARCHAR,"
            "s_nationkey INTEGER, s_phone VARCHAR, s_acctbal DOUBLE, s_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS partsupp ("
            "ps_partkey INTEGER, ps_suppkey INTEGER, ps_availqty INTEGER,"
            "ps_supplycost DOUBLE, ps_comment VARCHAR,"
            "PRIMARY KEY (ps_partkey, ps_suppkey))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS customer ("
            "c_custkey INTEGER PRIMARY KEY, c_name VARCHAR, c_address VARCHAR,"
            "c_nationkey INTEGER, c_phone VARCHAR, c_acctbal DOUBLE,"
            "c_mktsegment VARCHAR, c_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS region ("
            "r_regionkey INTEGER PRIMARY KEY, r_name VARCHAR, r_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS nation ("
            "n_nationkey INTEGER PRIMARY KEY, n_name VARCHAR,"
            "n_regionkey INTEGER, n_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS orders ("
            "o_orderkey INTEGER PRIMARY KEY, o_custkey INTEGER, o_orderstatus VARCHAR,"
            "o_totalprice DOUBLE, o_orderdate DATE, o_orderpriority VARCHAR,"
            "o_clerk VARCHAR, o_shippriority INTEGER, o_comment VARCHAR)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS lineitem ("
            "l_orderkey INTEGER, l_partkey INTEGER, l_suppkey INTEGER,"
            "l_linenumber INTEGER, l_quantity DOUBLE, l_extendedprice DOUBLE,"
            "l_discount DOUBLE, l_tax DOUBLE, l_returnflag VARCHAR,"
            "l_linestatus VARCHAR, l_shipdate DATE, l_commitdate DATE,"
            "l_receiptdate DATE, l_shipinstruct VARCHAR, l_shipmode VARCHAR,"
            "l_comment VARCHAR, PRIMARY KEY (l_orderkey, l_linenumber))"
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
            "INSERT INTO part VALUES"
            "(1, 'goldenrod lace spring', 'Manufacturer#1', 'Brand#13', 'PROMO BURNISHED COPPER', 7, 'JUMBO PKG', 901.00, 'furiously regular requests'),"
            "(2, 'blush forest saddle', 'Manufacturer#1', 'Brand#13', 'LARGE BRUSHED BRASS', 1, 'LG CASE', 902.00, 'lar accounts with the special instructions'),"
            "(3, 'dark green antique puff', 'Manufacturer#4', 'Brand#42', 'STANDARD POLISHED BRASS', 21, 'WRAP CASE', 903.00, 'dual pinto beans against the'),"
            "(4, 'hot lace khaki', 'Manufacturer#3', 'Brand#34', 'SMALL PLATED BRASS', 14, 'MED BAG', 904.00, 'the stealthy requests'),"
            "(5, 'spring indian chiffon', 'Manufacturer#3', 'Brand#35', 'PROMO BRUSHED STEEL', 7, 'SM PKG', 905.00, 'c deposits boost slyly')"
        )
        conn.execute(
            "INSERT INTO supplier VALUES"
            "(1, 'Supplier#000000001', 'N kD4on9OM Ipw3,gf0JBoq', 17, '27-918-335-1736', 5755.94, 'final deposits among the slyly express gifts'),"
            "(2, 'Supplier#000000002', '89eJ5ksX3ImxJQBvxObC,', 5, '15-679-861-2259', 4032.68, 'blithely bold packages express'),"
            "(3, 'Supplier#000000003', 'gyCsewaC4p', 1, '11-383-516-1199', 4192.40, 'carefully final packages cajole fluffily'),"
            "(4, 'Supplier#000000004', 'kTGpJqO8HOrfbh', 14, '24-696-997-4969', 5300.37, 'slyly bold dependencies wake'),"
            "(5, 'Supplier#000000005', 'd8eFhrA8b', 9, '19-393-671-5272', 8014.30, 'closely express theodolites across the')"
        )
        conn.execute(
            "INSERT INTO partsupp VALUES"
            "(1, 2, 3325, 771.64, 'furiously even instructions.'),"
            "(1, 3, 8076, 993.49, 'luffily according to the slyly regular packages.'),"
            "(2, 3, 3956, 337.09, 'carefully pending pinto beans.'),"
            "(3, 4, 4069, 905.44, 'ending packages.'),"
            "(4, 3, 8895, 378.49, 'cording to the final, final theodolites.')"
        )
        conn.execute(
            "INSERT INTO customer VALUES"
            "(1, 'Customer#000000001', 'IVhzIApeRb ot,c,E', 15, '25-989-741-2988', 711.56, 'BUILDING', 'furiously even instructions'),"
            "(2, 'Customer#000000002', 'XSTf4,NCwDVaWNe6tEgvw', 13, '23-768-687-3665', 121.65, 'AUTOMOBILE', 'the slyly bold accounts.'),"
            "(3, 'Customer#000000003', 'MG9kdTD2WBHm', 1, '11-719-748-3364', 7498.12, 'FURNITURE', 'posits sleep slyly'),"
            "(4, 'Customer#000000004', 'XxVSyxsKBtn', 4, '14-128-190-5944', 2866.83, 'MACHINERY', 'ackages. accounts'),"
            "(5, 'Customer#000000005', 'KvpyuHCplrB84W', 17, '27-750-860-3807', 5864.25, 'BUILDING', 'lyly express accounts.')"
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
    print("  tpch_duckdb.db — created (8 TPC-H tables)")


def _read_init_sql(path: str) -> str:
    base = os.path.dirname(__file__) or "."
    with open(os.path.join(base, path)) as f:
        return f.read()


def main() -> None:
    ensure_dir(DATA_DIR)

    create_test_sqlite()
    create_cross_sqlite_a()
    create_cross_sqlite_b()
    create_tpch_sqlite()
    create_tpch_sqlflite()
    create_tpch_duckdb()

    print("\nAll data files generated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
