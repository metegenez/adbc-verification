-- TPC-H Q06: Forecasting Revenue Change
-- Catalog: sr_postgres, Schema: public
-- Expected: 1 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    SUM(l_extendedprice * l_discount) AS revenue
FROM sr_postgres.public.lineitem
WHERE l_shipdate >= '1994-01-01'
  AND l_shipdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
  AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01
  AND l_quantity < 24;
