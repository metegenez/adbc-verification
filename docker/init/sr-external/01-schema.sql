-- StarRocks init: TPC-H schema for sr-external (sr_flightsql_starrocks catalog target)
-- Idempotent via IF NOT EXISTS. Re-runnable on warm boots.
-- Backend: sr-external FE+BE container, MySQL protocol on port 9030 (Docker-internal).

CREATE DATABASE IF NOT EXISTS tpch;
USE tpch;

CREATE TABLE IF NOT EXISTS region (
    r_regionkey INT NOT NULL,
    r_name VARCHAR(25) NOT NULL,
    r_comment VARCHAR(152)
)
DISTRIBUTED BY HASH(r_regionkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS nation (
    n_nationkey INT NOT NULL,
    n_name VARCHAR(25) NOT NULL,
    n_regionkey INT NOT NULL,
    n_comment VARCHAR(152)
)
DISTRIBUTED BY HASH(n_nationkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS supplier (
    s_suppkey INT NOT NULL,
    s_name VARCHAR(25) NOT NULL,
    s_address VARCHAR(40) NOT NULL,
    s_nationkey INT NOT NULL,
    s_phone VARCHAR(15) NOT NULL,
    s_acctbal DECIMAL(15, 2) NOT NULL,
    s_comment VARCHAR(101)
)
DISTRIBUTED BY HASH(s_suppkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS part (
    p_partkey INT NOT NULL,
    p_name VARCHAR(55) NOT NULL,
    p_mfgr VARCHAR(25) NOT NULL,
    p_brand VARCHAR(10) NOT NULL,
    p_type VARCHAR(25) NOT NULL,
    p_size INT NOT NULL,
    p_container VARCHAR(10) NOT NULL,
    p_retailprice DECIMAL(15, 2) NOT NULL,
    p_comment VARCHAR(23)
)
DISTRIBUTED BY HASH(p_partkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS partsupp (
    ps_partkey INT NOT NULL,
    ps_suppkey INT NOT NULL,
    ps_availqty INT NOT NULL,
    ps_supplycost DECIMAL(15, 2) NOT NULL,
    ps_comment VARCHAR(199)
)
DISTRIBUTED BY HASH(ps_partkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS customer (
    c_custkey INT NOT NULL,
    c_name VARCHAR(25) NOT NULL,
    c_address VARCHAR(40) NOT NULL,
    c_nationkey INT NOT NULL,
    c_phone VARCHAR(15) NOT NULL,
    c_acctbal DECIMAL(15, 2) NOT NULL,
    c_mktsegment VARCHAR(10) NOT NULL,
    c_comment VARCHAR(117) NOT NULL
)
DISTRIBUTED BY HASH(c_custkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS orders (
    o_orderkey INT NOT NULL,
    o_custkey INT NOT NULL,
    o_orderstatus CHAR(1) NOT NULL,
    o_totalprice DECIMAL(15, 2) NOT NULL,
    o_orderdate DATE NOT NULL,
    o_orderpriority VARCHAR(15) NOT NULL,
    o_clerk VARCHAR(15) NOT NULL,
    o_shippriority INT NOT NULL,
    o_comment VARCHAR(79) NOT NULL
)
DISTRIBUTED BY HASH(o_orderkey)
PROPERTIES('replication_num' = '1');

CREATE TABLE IF NOT EXISTS lineitem (
    l_orderkey INT NOT NULL,
    l_partkey INT NOT NULL,
    l_suppkey INT NOT NULL,
    l_linenumber INT NOT NULL,
    l_quantity DECIMAL(15, 2) NOT NULL,
    l_extendedprice DECIMAL(15, 2) NOT NULL,
    l_discount DECIMAL(15, 2) NOT NULL,
    l_tax DECIMAL(15, 2) NOT NULL,
    l_returnflag CHAR(1) NOT NULL,
    l_linestatus CHAR(1) NOT NULL,
    l_shipdate DATE NOT NULL,
    l_commitdate DATE NOT NULL,
    l_receiptdate DATE NOT NULL,
    l_shipinstruct VARCHAR(25) NOT NULL,
    l_shipmode VARCHAR(10) NOT NULL,
    l_comment VARCHAR(44) NOT NULL
)
DISTRIBUTED BY HASH(l_orderkey)
PROPERTIES('replication_num' = '1');
