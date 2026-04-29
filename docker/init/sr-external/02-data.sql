-- StarRocks init: TPC-H SF1 bulk data load for sr-external via FILES() table function.
-- Idempotent: TRUNCATE + re-import on every container start.
-- Backend: sr-external FE+BE; CSVs bind-mounted at /opt/starrocks/data/sf1/ (read-only).

USE tpch;

TRUNCATE TABLE region;
INSERT INTO region
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/region.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE nation;
INSERT INTO nation
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/nation.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE supplier;
INSERT INTO supplier
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/supplier.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE part;
INSERT INTO part
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/part.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE partsupp;
INSERT INTO partsupp
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/partsupp.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE customer;
INSERT INTO customer
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/customer.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE orders;
INSERT INTO orders
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/orders.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);

TRUNCATE TABLE lineitem;
INSERT INTO lineitem
SELECT * FROM FILES(
    'path' = 'file:///opt/starrocks/data/sf1/lineitem.csv',
    'format' = 'csv',
    'csv.skip_header' = '1',
    'csv.column_separator' = ',',
    'csv.enclose' = '"'
);
