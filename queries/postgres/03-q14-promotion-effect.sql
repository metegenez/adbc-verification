-- TPC-H Q14: Promotion Effect
-- Catalog: sr_postgres, Schema: public
-- Expected: 1 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    100.00 * SUM(CASE WHEN p_type LIKE 'PROMO%'
                      THEN l_extendedprice * (1 - l_discount)
                      ELSE 0 END)
    / SUM(l_extendedprice * (1 - l_discount)) AS promo_revenue
FROM sr_postgres.public.lineitem
JOIN sr_postgres.public.part ON l_partkey = p_partkey
WHERE l_shipdate >= '1995-09-01'
  AND l_shipdate < DATE_ADD('1995-09-01', INTERVAL 1 MONTH);
