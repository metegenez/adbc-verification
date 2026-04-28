#!/usr/bin/env python3
"""
TPC-H SF1 data generator for PostgreSQL and MySQL backends.

Generates 8 CSV files with TPC-H Scale Factor 1 row counts:
  region   (5), nation     (25),     part      (200,000),
  supplier (10,000),       partsupp  (800,000), customer  (150,000),
  orders   (1,500,000),    lineitem  (~6,000,121)

Output: docker/data/sf1/  (relative to this script's directory)

Usage:
    cd docker && python generate-sf1-data.py

Requires: Python 3.8+ stdlib only (csv, random, datetime, os, sys, gzip)
"""

import csv
import os
import random
import sys
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Fixed seed — ensures reproducible output across runs and machines
# ---------------------------------------------------------------------------
random.seed(42)

# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCRIPT_DIR, "data", "sf1")
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# TPC-H SF1 target row counts
# ---------------------------------------------------------------------------
REGION_ROWS    = 5
NATION_ROWS    = 25
SUPPLIER_ROWS  = 10_000
PART_ROWS      = 200_000
PARTSUPP_ROWS  = 800_000     # 4 suppliers per part
CUSTOMER_ROWS  = 150_000
ORDERS_ROWS    = 1_500_000
LINEITEM_ROWS  = 6_000_121   # approximated — actual count depends on lineitems/order

# ---------------------------------------------------------------------------
# TPC-H vocabulary sets (per spec / common implementations)
# ---------------------------------------------------------------------------

REGIONS = [
    (0, "AFRICA",      "lar deposits. blithely final packages cajole."),
    (1, "AMERICA",     "hs use ironic, even requests."),
    (2, "ASIA",        "ges. thinly even pinto beans ca"),
    (3, "EUROPE",      "ly final courts cajole furiously final excuse"),
    (4, "MIDDLE EAST", "uickly special accounts cajole carefully blithely close"),
]

NATIONS = [
    (0,  "ALGERIA",        0,  "furiously regular deposits"),
    (1,  "ARGENTINA",      1,  "al foxes promise"),
    (2,  "BRAZIL",         1,  "y alongside of the pending deposits"),
    (3,  "CANADA",         1,  "eas hang ironic"),
    (4,  "EGYPT",          4,  "y above the carefully unusual theodolites"),
    (5,  "ETHIOPIA",       0,  "ven packages wake quickly"),
    (6,  "FRANCE",         3,  "refully final requests"),
    (7,  "GERMANY",        3,  "l platelets. regular accounts x-ray"),
    (8,  "INDIA",          2,  "ss excuses cajole slyly across the packages"),
    (9,  "INDONESIA",      2,  "slyly express asymptotes"),
    (10, "IRAN",           4,  "efully alongside of the slyly final dependencies"),
    (11, "IRAQ",           4,  "nic deposits boost atop the quickly final requests"),
    (12, "JAPAN",          2,  "ously. final, express gifts cajole a"),
    (13, "JORDAN",         4,  "ic deposits are blithely about the carefully regular"),
    (14, "KENYA",          0,  "pending excuses haggle furiously deposits"),
    (15, "MOROCCO",        0,  "rns. blithely bold courts among the closely regular"),
    (16, "MOZAMBIQUE",     0,  "s. ironic, unusual asymptotes wake blithely r"),
    (17, "PERU",           1,  "platelets. blithely pending dependencies use fluffily"),
    (18, "CHINA",          2,  "c dependencies. furiously express notornis sleep slyly"),
    (19, "ROMANIA",        3,  "ular asymptotes are about the furious multipliers"),
    (20, "SAUDI ARABIA",   4,  "ts. silent requests haggle. closely express packages"),
    (21, "VIETNAM",        2,  "hely enticingly express accounts. even, final"),
    (22, "RUSSIA",         3,  "requests against the platelets use never according to the"),
    (23, "UNITED KINGDOM", 3,  "eans boost carefully special requests"),
    (24, "UNITED STATES",  1,  "y final packages. slow foxes cajole quickly"),
]

# Part name vocabulary (TPC-H spec lists)
PART_COLORS = [
    "almond", "antique", "aquamarine", "azure", "beige", "bisque", "black",
    "blanched", "blue", "blush", "brown", "burlywood", "burnished", "chartreuse",
    "chiffon", "chocolate", "coral", "cornflower", "cornsilk", "cream", "cyan",
    "dark", "deep", "dodger", "drab", "firebrick", "floral", "forest", "frosted",
    "gainsboro", "ghost", "goldenrod", "green", "grey", "honeydew", "hot",
    "indian", "ivory", "khaki", "lace", "lavender", "lawn", "lemon", "light",
    "lime", "linen", "magenta", "maroon", "medium", "metallic", "midnight",
    "mint", "misty", "moccasin", "navajo", "navy", "olive", "orange", "orchid",
    "pale", "papaya", "peach", "peru", "pink", "plum", "powder", "puff",
    "purple", "red", "rose", "rosy", "royal", "saddle", "salmon", "sandy",
    "seashell", "sienna", "sky", "slate", "smoke", "snow", "spring", "steel",
    "tan", "thistle", "tomato", "turquoise", "violet", "wheat", "white", "yellow",
]

# Part type vocabulary
PART_TYPE_SIZE = ["SMALL", "MEDIUM", "LARGE", "JUMBO", "ECONOMY"]
PART_TYPE_MATERIAL = ["ANODIZED", "BURNISHED", "PLATED", "POLISHED", "BRUSHED"]
PART_TYPE_FINISH = ["TIN", "NICKEL", "BRASS", "STEEL", "COPPER"]

# Container vocabulary
PART_CONTAINER_SIZE = ["SM", "LG", "MED", "JUMBO", "WRAP"]
PART_CONTAINER_TYPE = ["CASE", "BOX", "BAG", "JAR", "PKG", "PACK", "CAN", "DRUM"]

# Market segments
MARKET_SEGMENTS = ["AUTOMOBILE", "BUILDING", "FURNITURE", "MACHINERY", "HOUSEHOLD"]

# Order priorities
ORDER_PRIORITIES = ["1-URGENT", "2-HIGH", "3-MEDIUM", "4-NOT SPECIFIED", "5-LOW"]

# Ship instructions
SHIP_INSTRUCT = ["DELIVER IN PERSON", "COLLECT COD", "NONE", "TAKE BACK RETURN"]

# Ship modes
SHIP_MODES = ["REG AIR", "AIR", "RAIL", "SHIP", "TRUCK", "MAIL", "FOB"]

# Retailprice formula: 90000 + ((p_partkey / 10) modulo 20001) + (p_partkey modulo 1000) * 0.01
def part_retailprice(partkey: int) -> float:
    return round(90000 + ((partkey // 10) % 20001) + (partkey % 1000) * 0.01, 2)

def rand_word() -> str:
    """Random lorem-ipsum style word from TPC-H comment vocabulary."""
    words = [
        "quickly", "fluffily", "slyly", "blithely", "furiously", "ironic",
        "unusual", "special", "regular", "pending", "final", "express",
        "silent", "bold", "close", "careful", "ruthless", "even", "thin",
        "deposits", "accounts", "packages", "requests", "instructions",
        "courts", "foxes", "pinto beans", "asymptotes", "theodolites",
        "platelets", "dependencies", "excuses", "frays", "warthogs", "ideas",
        "warhorses", "gifts", "grouches", "stealthy", "cajole", "haggle",
        "wake", "sleep", "are", "use", "nag", "among", "above", "alongside",
        "according to", "around", "about", "across", "after", "against",
    ]
    return random.choice(words)

def rand_comment(min_len: int = 20, max_len: int = 60) -> str:
    """Generate a TPC-H-style comment of at least min_len characters."""
    comment = rand_word()
    while len(comment) < min_len:
        comment += " " + rand_word()
    return comment[:max_len]

def rand_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))

# ---------------------------------------------------------------------------
# Date constants
# ---------------------------------------------------------------------------
DATE_START = date(1992, 1, 1)
DATE_END   = date(1998, 12, 31)

# ---------------------------------------------------------------------------
# Helper: open CSV writer (uncompressed for init script compatibility)
# ---------------------------------------------------------------------------
def open_csv(name: str) -> tuple:
    """Return (file_handle, csv.writer) for the given table name."""
    path = os.path.join(OUT_DIR, f"{name}.csv")
    fh = open(path, "w", newline="", encoding="utf-8")
    writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
    return fh, writer, path

# ---------------------------------------------------------------------------
# Table generators
# ---------------------------------------------------------------------------

def gen_region():
    print("  Generating region...", end=" ", flush=True)
    fh, w, path = open_csv("region")
    w.writerow(["r_regionkey", "r_name", "r_comment"])
    for row in REGIONS:
        w.writerow(row)
    fh.close()
    count = len(REGIONS)
    print(f"{count:,} rows  -> {path}")
    return count

def gen_nation():
    print("  Generating nation...", end=" ", flush=True)
    fh, w, path = open_csv("nation")
    w.writerow(["n_nationkey", "n_name", "n_regionkey", "n_comment"])
    for row in NATIONS:
        w.writerow(row)
    fh.close()
    count = len(NATIONS)
    print(f"{count:,} rows  -> {path}")
    return count

def gen_supplier():
    print("  Generating supplier...", end=" ", flush=True)
    fh, w, path = open_csv("supplier")
    w.writerow(["s_suppkey", "s_name", "s_address", "s_nationkey", "s_phone", "s_acctbal", "s_comment"])
    count = 0
    for s in range(1, SUPPLIER_ROWS + 1):
        nationkey = random.randint(0, 24)
        # phone: CC-NNN-NNN-NNNN format per TPC-H spec (CC from nation)
        phone = f"{nationkey:02d}-{random.randint(100,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"
        acctbal = round(random.uniform(-999.99, 9999.99), 2)
        address_len = random.randint(10, 40)
        address = rand_comment(10, address_len)
        w.writerow([
            s,
            f"Supplier#{s:09d}",
            address,
            nationkey,
            phone,
            f"{acctbal:.2f}",
            rand_comment(25, 101),
        ])
        count += 1
    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

def gen_part():
    """Returns dict of partkey -> retailprice for partsupp/lineitem use."""
    print("  Generating part...", end=" ", flush=True)
    fh, w, path = open_csv("part")
    w.writerow(["p_partkey", "p_name", "p_mfgr", "p_brand", "p_type", "p_size", "p_container", "p_retailprice", "p_comment"])
    count = 0
    # We pre-sample retail prices (deterministic from key)
    for p in range(1, PART_ROWS + 1):
        # Name: 5 distinct colors joined by space (TPC-H uses word-draw-without-replacement per part)
        sample = random.sample(PART_COLORS, min(5, len(PART_COLORS)))
        name = " ".join(sample[:5])
        mfgr_num = random.randint(1, 5)
        brand_num = random.randint(1, 5)
        p_type = (
            random.choice(PART_TYPE_SIZE)
            + " " + random.choice(PART_TYPE_MATERIAL)
            + " " + random.choice(PART_TYPE_FINISH)
        )
        size = random.randint(1, 50)
        container = random.choice(PART_CONTAINER_SIZE) + " " + random.choice(PART_CONTAINER_TYPE)
        retailprice = part_retailprice(p)
        w.writerow([
            p,
            name,
            f"Manufacturer#{mfgr_num}",
            f"Brand#{mfgr_num}{brand_num}",
            p_type,
            size,
            container,
            f"{retailprice:.2f}",
            rand_comment(5, 23),
        ])
        count += 1
    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

def gen_partsupp():
    """Generate 4 suppliers per part = 800,000 rows."""
    print("  Generating partsupp...", end=" ", flush=True)
    fh, w, path = open_csv("partsupp")
    w.writerow(["ps_partkey", "ps_suppkey", "ps_availqty", "ps_supplycost", "ps_comment"])
    count = 0
    # For each part, choose 4 distinct suppliers
    for p in range(1, PART_ROWS + 1):
        # TPC-H: s = (p + (i * ((S/4) + (int)(p-1)/S))) mod S + 1
        S = SUPPLIER_ROWS
        suppliers_for_part = set()
        for i in range(4):
            suppkey = ((p - 1 + i * ((S // 4) + (p - 1) // S)) % S) + 1
            suppliers_for_part.add(suppkey)
        # fill to 4 if collision (rare)
        while len(suppliers_for_part) < 4:
            suppliers_for_part.add(random.randint(1, SUPPLIER_ROWS))
        for suppkey in sorted(suppliers_for_part):
            availqty = random.randint(1, 9999)
            supplycost = round(random.uniform(1.00, 1000.00), 2)
            w.writerow([p, suppkey, availqty, f"{supplycost:.2f}", rand_comment(49, 199)])
            count += 1
    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

def gen_customer():
    print("  Generating customer...", end=" ", flush=True)
    fh, w, path = open_csv("customer")
    w.writerow(["c_custkey", "c_name", "c_address", "c_nationkey", "c_phone", "c_acctbal", "c_mktsegment", "c_comment"])
    count = 0
    for c in range(1, CUSTOMER_ROWS + 1):
        nationkey = random.randint(0, 24)
        phone = f"{nationkey:02d}-{random.randint(100,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}"
        acctbal = round(random.uniform(-999.99, 9999.99), 2)
        w.writerow([
            c,
            f"Customer#{c:09d}",
            rand_comment(10, 40),
            nationkey,
            phone,
            f"{acctbal:.2f}",
            random.choice(MARKET_SEGMENTS),
            rand_comment(29, 117),
        ])
        count += 1
    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

def gen_orders():
    """
    Returns set of valid (orderkey, custkey) for lineitem generation.
    """
    print("  Generating orders...", end=" ", flush=True)
    fh, w, path = open_csv("orders")
    w.writerow(["o_orderkey", "o_custkey", "o_orderstatus", "o_totalprice",
                "o_orderdate", "o_orderpriority", "o_clerk", "o_shippriority", "o_comment"])

    # TPC-H orderstatus weights: F=0.40, O=0.41, P=0.19 (approximately)
    # We'll use weighted random choice
    statuses = ["F"] * 40 + ["O"] * 41 + ["P"] * 19
    count = 0
    for o in range(1, ORDERS_ROWS + 1):
        custkey = random.randint(1, CUSTOMER_ROWS)
        status = random.choice(statuses)
        totalprice = round(random.uniform(1000.00, 500000.00), 2)
        orderdate = rand_date(DATE_START, date(1998, 8, 2))
        priority = random.choice(ORDER_PRIORITIES)
        clerk_num = random.randint(1, 1000)
        w.writerow([
            o,
            custkey,
            status,
            f"{totalprice:.2f}",
            orderdate.isoformat(),
            priority,
            f"Clerk#{clerk_num:09d}",
            0,
            rand_comment(19, 79),
        ])
        count += 1
    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

def gen_lineitem():
    """
    Generate ~6,000,121 lineitem rows.
    Strategy: assign 1-7 lineitems per order until target is reached.
    Use a pre-build partsupp lookup: for each part, which suppliers exist.
    """
    print("  Generating lineitem (this takes a few minutes)...", end=" ", flush=True)
    sys.stdout.flush()

    # Build partsupp supplier mapping in memory
    # partsupp has 4 suppliers per part; we can compute on the fly (same formula as gen_partsupp)
    def suppkeys_for_part(p: int) -> list:
        S = SUPPLIER_ROWS
        suppliers = set()
        for i in range(4):
            suppkey = ((p - 1 + i * ((S // 4) + (p - 1) // S)) % S) + 1
            suppliers.add(suppkey)
        while len(suppliers) < 4:
            suppliers.add(random.randint(1, SUPPLIER_ROWS))
        return sorted(suppliers)

    fh, w, path = open_csv("lineitem")
    w.writerow([
        "l_orderkey", "l_partkey", "l_suppkey", "l_linenumber",
        "l_quantity", "l_extendedprice", "l_discount", "l_tax",
        "l_returnflag", "l_linestatus",
        "l_shipdate", "l_commitdate", "l_receiptdate",
        "l_shipinstruct", "l_shipmode", "l_comment",
    ])

    # returnflag weights: N=0.70, A=0.05, R=0.25 (simplified — exact depends on ship date vs cutoff)
    returnflags_N = ["N"] * 70 + ["A"] * 5 + ["R"] * 25

    TARGET = LINEITEM_ROWS
    count = 0
    orderkey = 0

    while count < TARGET:
        orderkey += 1
        if orderkey > ORDERS_ROWS:
            # Wrap around if we haven't hit the target (shouldn't happen at SF1)
            orderkey = 1

        # 1-7 lineitems per order (average ~4.0 gives 6M from 1.5M orders)
        # Weighted toward 3-7 to hit 6M target
        num_lines = random.choices(
            [1, 2, 3, 4, 5, 6, 7],
            weights=[5, 8, 12, 15, 20, 20, 20],
        )[0]

        orderdate = rand_date(DATE_START, date(1998, 8, 2))

        for linenumber in range(1, num_lines + 1):
            if count >= TARGET:
                break

            partkey = random.randint(1, PART_ROWS)
            suppkeys = suppkeys_for_part(partkey)
            suppkey = random.choice(suppkeys)

            quantity = round(random.uniform(1.0, 50.0), 2)
            retailprice = part_retailprice(partkey)
            extendedprice = round(quantity * retailprice, 2)
            discount = round(random.uniform(0.00, 0.10), 2)
            tax = round(random.uniform(0.00, 0.08), 2)

            # Ship date: orderdate + 1..121 days
            shipdate = orderdate + timedelta(days=random.randint(1, 121))
            # Commit date: orderdate + 30..90 days
            commitdate = orderdate + timedelta(days=random.randint(30, 90))
            # Receipt date: shipdate + 1..30 days
            receiptdate = shipdate + timedelta(days=random.randint(1, 30))

            # returnflag: N if not yet returned, else R or A
            if shipdate > date(1998, 12, 1):
                returnflag = "N"
            else:
                returnflag = random.choice(returnflags_N)
            linestatus = "O" if shipdate > date(1998, 12, 1) else "F"

            w.writerow([
                orderkey,
                partkey,
                suppkey,
                linenumber,
                f"{quantity:.2f}",
                f"{extendedprice:.2f}",
                f"{discount:.2f}",
                f"{tax:.2f}",
                returnflag,
                linestatus,
                shipdate.isoformat(),
                commitdate.isoformat(),
                receiptdate.isoformat(),
                random.choice(SHIP_INSTRUCT),
                random.choice(SHIP_MODES),
                rand_comment(10, 44),
            ])
            count += 1

    fh.close()
    print(f"{count:,} rows  -> {path}")
    return count

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"TPC-H SF1 Data Generator")
    print(f"Output directory: {OUT_DIR}")
    print()

    counts = {}
    counts["region"]   = gen_region()
    counts["nation"]   = gen_nation()
    counts["supplier"] = gen_supplier()
    counts["part"]     = gen_part()
    counts["partsupp"] = gen_partsupp()
    counts["customer"] = gen_customer()
    counts["orders"]   = gen_orders()
    counts["lineitem"] = gen_lineitem()

    print()
    print("=== Row Count Summary ===")
    expected = {
        "region":   REGION_ROWS,
        "nation":   NATION_ROWS,
        "supplier": SUPPLIER_ROWS,
        "part":     PART_ROWS,
        "partsupp": PARTSUPP_ROWS,
        "customer": CUSTOMER_ROWS,
        "orders":   ORDERS_ROWS,
        "lineitem": LINEITEM_ROWS,
    }
    all_ok = True
    for table, count in counts.items():
        exp = expected[table]
        status = "OK" if count == exp else f"MISMATCH (expected {exp:,})"
        if count != exp:
            all_ok = False
        print(f"  {table:10s}: {count:>10,}  {status}")

    print()
    print("=== File Sizes ===")
    for table in counts:
        path = os.path.join(OUT_DIR, f"{table}.csv")
        size = os.path.getsize(path)
        print(f"  {table:10s}: {size / 1024 / 1024:.1f} MB  ({path})")

    print()
    if all_ok:
        print("All row counts match TPC-H SF1 specification.")
    else:
        print("WARNING: Some row counts do not match TPC-H SF1 spec — check output above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
