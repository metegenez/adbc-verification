-- TPC-H Q18: Large Volume Customer
-- Expected (mysql): 57 rows
-- Expected (flightsql-starrocks): 57 rows
SELECT
    c_name,
    c_custkey,
    o_orderkey,
    o_orderdate,
    o_totalprice,
    SUM(l_quantity)
FROM {catalog}.{db}.customer
JOIN {catalog}.{db}.orders   ON c_custkey = o_custkey
JOIN {catalog}.{db}.lineitem ON o_orderkey = l_orderkey
WHERE o_orderkey IN (
    SELECT l_orderkey
    FROM {catalog}.{db}.lineitem
    GROUP BY l_orderkey
    HAVING SUM(l_quantity) > 300
)
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice DESC, o_orderdate
LIMIT 100;
