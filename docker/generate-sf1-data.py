#!/usr/bin/env python3
"""
TPC-H SF1 CSV generator using DuckDB's bundled tpch extension.

Replaces the 503-line hand-rolled generator (Phase 2) with the canonical
TPC-H dbgen distribution shipped via DuckDB. Output is deterministic for a
given scale factor.

Output: docker/data/sf1/<table>.csv (8 files), gitignored (~895 MB).

Format: comma-delimited, double-quote-enclosed on demand, LF line endings,
1-line header row. The header row is required by the existing consumers:
  - docker/init/postgres/02-data.sql      (uses HEADER true)
  - docker/init/mysql/02-data.sql         (uses IGNORE 1 ROWS)
  - docker/init/sr-external/02-data.sql   (plan 04-01; uses csv.skip_header='1')

Usage:
    cd docker && python3 generate-sf1-data.py
"""
import os
import duckdb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "data", "sf1")
os.makedirs(OUT_DIR, exist_ok=True)

con = duckdb.connect()
con.execute("INSTALL tpch")
con.execute("LOAD tpch")
con.execute("CALL dbgen(sf=1)")

TABLES = ["region", "nation", "supplier", "part", "partsupp",
          "customer", "orders", "lineitem"]
for table in TABLES:
    out_path = os.path.join(OUT_DIR, f"{table}.csv")
    con.execute(
        f"COPY {table} TO '{out_path}' "
        f"(FORMAT CSV, HEADER TRUE, DELIMITER ',')"
    )
    n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"  {table}: {n} rows -> {out_path}")
