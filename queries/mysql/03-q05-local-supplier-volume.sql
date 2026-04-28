-- TPC-H Q05: Local Supplier Volume
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 5 rows
SELECT
    n_name,
    SUM(l_extendedprice * (1 - l_discount)) AS revenue
FROM sr_mysql.testdb.customer
JOIN sr_mysql.testdb.orders   ON c_custkey = o_custkey
JOIN sr_mysql.testdb.lineitem ON l_orderkey = o_orderkey
JOIN sr_mysql.testdb.supplier ON l_suppkey = s_suppkey AND c_nationkey = s_nationkey
JOIN sr_mysql.testdb.nation   ON s_nationkey = n_nationkey
JOIN sr_mysql.testdb.region   ON n_regionkey = r_regionkey
WHERE r_name = 'ASIA'
  AND o_orderdate >= '1994-01-01'
  AND o_orderdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
GROUP BY n_name
ORDER BY revenue DESC;
