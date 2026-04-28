-- PostgreSQL init: Phase 2 — SF1 bulk data loading via COPY
-- Replaces seed data. Idempotent: TRUNCATE + re-import on every container start.
-- Non-TPC-H tables (test_data, departments) are preserved in 03-seed.sql.
--
-- Load order respects FK dependencies (parents before children):
--   region → nation → part, supplier → partsupp, customer → orders → lineitem

TRUNCATE region CASCADE;
TRUNCATE nation CASCADE;
TRUNCATE part CASCADE;
TRUNCATE supplier CASCADE;
TRUNCATE customer CASCADE;
TRUNCATE partsupp CASCADE;
TRUNCATE orders CASCADE;
TRUNCATE lineitem CASCADE;

\COPY region   FROM '/sf1-data/region.csv'   WITH (FORMAT csv, HEADER true);
\COPY nation   FROM '/sf1-data/nation.csv'   WITH (FORMAT csv, HEADER true);
\COPY part     FROM '/sf1-data/part.csv'     WITH (FORMAT csv, HEADER true);
\COPY supplier FROM '/sf1-data/supplier.csv' WITH (FORMAT csv, HEADER true);
\COPY customer FROM '/sf1-data/customer.csv' WITH (FORMAT csv, HEADER true);
\COPY partsupp FROM '/sf1-data/partsupp.csv' WITH (FORMAT csv, HEADER true);
\COPY orders   FROM '/sf1-data/orders.csv'   WITH (FORMAT csv, HEADER true);
\COPY lineitem FROM '/sf1-data/lineitem.csv' WITH (FORMAT csv, HEADER true);
