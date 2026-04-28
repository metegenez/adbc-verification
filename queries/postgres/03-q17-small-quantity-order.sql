-- TPC-H Q17: Small-Quantity-Order Revenue
-- Catalog: sr_postgres, Schema: public
-- Expected: 1 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    SUM(l_extendedprice) / 7.0 AS avg_yearly
FROM sr_postgres.public.lineitem
JOIN sr_postgres.public.part ON p_partkey = l_partkey
WHERE p_brand = 'Brand#23'
  AND p_container = 'MED BOX'
  AND l_quantity < (
      SELECT 0.2 * AVG(l_quantity)
      FROM sr_postgres.public.lineitem l2
      WHERE l2.l_partkey = p_partkey
  );
