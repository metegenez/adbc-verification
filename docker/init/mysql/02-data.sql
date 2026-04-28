-- MySQL init: Phase 2 — SF1 bulk data loading via LOAD DATA INFILE
-- Replaces seed data. Idempotent: TRUNCATE + re-import on every container start.
-- Non-TPC-H tables (test_data, departments) are preserved in 03-cross-join.sql.
--
-- Files are mounted at /var/lib/mysql-files/ (MySQL secure_file_priv default).
-- Load order respects FK dependencies (FK checks disabled for speed):
--   region → nation → part, supplier → partsupp, customer → orders → lineitem

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE region;
LOAD DATA INFILE '/var/lib/mysql-files/region.csv'
    INTO TABLE region
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE nation;
LOAD DATA INFILE '/var/lib/mysql-files/nation.csv'
    INTO TABLE nation
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE part;
LOAD DATA INFILE '/var/lib/mysql-files/part.csv'
    INTO TABLE part
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE supplier;
LOAD DATA INFILE '/var/lib/mysql-files/supplier.csv'
    INTO TABLE supplier
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE customer;
LOAD DATA INFILE '/var/lib/mysql-files/customer.csv'
    INTO TABLE customer
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE partsupp;
LOAD DATA INFILE '/var/lib/mysql-files/partsupp.csv'
    INTO TABLE partsupp
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE orders;
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
    INTO TABLE orders
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

TRUNCATE lineitem;
LOAD DATA INFILE '/var/lib/mysql-files/lineitem.csv'
    INTO TABLE lineitem
    FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
    LINES TERMINATED BY '\n'
    IGNORE 1 ROWS;

SET FOREIGN_KEY_CHECKS = 1;
