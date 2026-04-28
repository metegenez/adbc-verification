-- TPC-H Q18: Large Volume Customer
-- Catalog: sr_postgres, Schema: public
-- Expected: 57 rows
SELECT
    c_name,
    c_custkey,
    o_orderkey,
    o_orderdate,
    o_totalprice,
    SUM(l_quantity)
FROM sr_postgres.public.customer
JOIN sr_postgres.public.orders   ON c_custkey = o_custkey
JOIN sr_postgres.public.lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey IN (
    SELECT l_orderkey
    FROM sr_postgres.public.lineitem
    GROUP BY l_orderkey
    HAVING SUM(l_quantity) > 300
)
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice DESC, o_orderdate
LIMIT 100;
