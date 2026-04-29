-- TPC-H Q04: Order Priority Checking
-- Expected: 5 rows
SELECT
    o_orderpriority,
    COUNT(*) AS order_count
FROM {catalog}.{db}.orders
WHERE o_orderdate >= '1993-07-01'
  AND o_orderdate < DATE_ADD('1993-07-01', INTERVAL 3 MONTH)
  AND EXISTS (
      SELECT 1
      FROM {catalog}.{db}.lineitem
      WHERE l_orderkey = o_orderkey
        AND l_commitdate < l_receiptdate
  )
GROUP BY o_orderpriority
ORDER BY o_orderpriority;
