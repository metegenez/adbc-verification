-- TPC-H Q10: Returned Item Reporting
-- Catalog: sr_postgres, Schema: public
-- Expected: 20 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    c_custkey,
    c_name,
    SUM(l_extendedprice * (1 - l_discount)) AS revenue,
    c_acctbal,
    n_name,
    c_address,
    c_phone,
    c_comment
FROM sr_postgres.public.customer
JOIN sr_postgres.public.orders   ON c_custkey = o_custkey
JOIN sr_postgres.public.lineitem ON l_orderkey = o_orderkey
JOIN sr_postgres.public.nation   ON n_nationkey = c_nationkey
WHERE o_orderdate >= '1993-10-01'
  AND o_orderdate < DATE_ADD('1993-10-01', INTERVAL 3 MONTH)
  AND l_returnflag = 'R'
GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment
ORDER BY revenue DESC
LIMIT 20;
