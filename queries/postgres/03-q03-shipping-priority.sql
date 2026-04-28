-- TPC-H Q03: Shipping Priority
-- Catalog: sr_postgres, Schema: public
-- Expected: 10 rows
SELECT
    l_orderkey,
    SUM(l_extendedprice * (1 - l_discount)) AS revenue,
    o_orderdate,
    o_shippriority
FROM sr_postgres.public.customer
JOIN sr_postgres.public.orders ON c_custkey = o_custkey
JOIN sr_postgres.public.lineitem ON l_orderkey = o_orderkey
WHERE c_mktsegment = 'BUILDING'
  AND o_orderdate < '1995-03-15'
  AND l_shipdate > '1995-03-15'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC, o_orderdate
LIMIT 10;
