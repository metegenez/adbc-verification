-- MySQL init: schema (idempotent via IF NOT EXISTS)
-- Backend service: sr-mysql (mysql:8.0, user=root, db=testdb)

CREATE TABLE IF NOT EXISTS region (
    r_regionkey INT PRIMARY KEY,
    r_name VARCHAR(25) NOT NULL,
    r_comment VARCHAR(152)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS nation (
    n_nationkey INT PRIMARY KEY,
    n_name VARCHAR(25) NOT NULL,
    n_regionkey INT NOT NULL,
    n_comment VARCHAR(152)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
    o_orderkey INT PRIMARY KEY,
    o_custkey INT NOT NULL,
    o_orderstatus CHAR(1) NOT NULL,
    o_totalprice DECIMAL(15,2) NOT NULL,
    o_orderdate DATE NOT NULL,
    o_orderpriority VARCHAR(15) NOT NULL,
    o_clerk VARCHAR(15) NOT NULL,
    o_shippriority INT NOT NULL,
    o_comment VARCHAR(79)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS lineitem (
    l_orderkey INT NOT NULL,
    l_partkey INT NOT NULL,
    l_suppkey INT NOT NULL,
    l_linenumber INT NOT NULL,
    l_quantity DECIMAL(15,2) NOT NULL,
    l_extendedprice DECIMAL(15,2) NOT NULL,
    l_discount DECIMAL(15,2) NOT NULL,
    l_tax DECIMAL(15,2) NOT NULL,
    l_returnflag CHAR(1) NOT NULL,
    l_linestatus CHAR(1) NOT NULL,
    l_shipdate DATE NOT NULL,
    l_commitdate DATE NOT NULL,
    l_receiptdate DATE NOT NULL,
    l_shipinstruct VARCHAR(25) NOT NULL,
    l_shipmode VARCHAR(10) NOT NULL,
    l_comment VARCHAR(44) NOT NULL,
    PRIMARY KEY (l_orderkey, l_linenumber)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS test_data (
    id INT PRIMARY KEY,
    name VARCHAR(50),
    value DOUBLE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS departments (
    dept_id INT PRIMARY KEY,
    dept_name VARCHAR(50)
) ENGINE=InnoDB;
