-- TPC-H Q05: Local Supplier Volume
-- Catalog: sr_postgres, Schema: public
-- Expected: 5 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    n_name,
    SUM(l_extendedprice * (1 - l_discount)) AS revenue
FROM sr_postgres.public.customer
JOIN sr_postgres.public.orders  ON c_custkey = o_custkey
JOIN sr_postgres.public.lineitem ON l_orderkey = o_orderkey
JOIN sr_postgres.public.supplier ON l_suppkey = s_suppkey AND c_nationkey = s_nationkey
JOIN sr_postgres.public.nation  ON s_nationkey = n_nationkey
JOIN sr_postgres.public.region  ON n_regionkey = r_regionkey
WHERE r_name = 'ASIA'
  AND o_orderdate >= '1994-01-01'
  AND o_orderdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
GROUP BY n_name
ORDER BY revenue DESC;
