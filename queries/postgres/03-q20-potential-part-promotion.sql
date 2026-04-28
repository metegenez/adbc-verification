-- TPC-H Q20: Potential Part Promotion
-- Catalog: sr_postgres, Schema: public
-- Expected: 186 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    s_name,
    s_address
FROM sr_postgres.public.supplier
JOIN sr_postgres.public.nation ON n_nationkey = s_nationkey
WHERE n_name = 'CANADA'
  AND s_suppkey IN (
      SELECT ps_suppkey
      FROM sr_postgres.public.partsupp
      WHERE ps_partkey IN (
          SELECT p_partkey
          FROM sr_postgres.public.part
          WHERE p_name LIKE 'forest%'
      )
      AND ps_availqty > (
          SELECT 0.5 * SUM(l_quantity)
          FROM sr_postgres.public.lineitem
          WHERE l_partkey = ps_partkey
            AND l_suppkey = ps_suppkey
            AND l_shipdate >= '1994-01-01'
            AND l_shipdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
      )
  )
ORDER BY s_name;
