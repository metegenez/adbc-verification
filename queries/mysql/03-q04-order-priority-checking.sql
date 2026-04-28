-- TPC-H Q04: Order Priority Checking
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 5 rows
SELECT
    o_orderpriority,
    COUNT(*) AS order_count
FROM sr_mysql.testdb.orders
WHERE o_orderdate >= '1993-07-01'
  AND o_orderdate < DATE_ADD('1993-07-01', INTERVAL 3 MONTH)
  AND EXISTS (
      SELECT 1
      FROM sr_mysql.testdb.lineitem
      WHERE l_orderkey = o_orderkey
        AND l_commitdate < l_receiptdate
  )
GROUP BY o_orderpriority
ORDER BY o_orderpriority;
