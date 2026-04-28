-- TPC-H Q21: Suppliers Who Kept Orders Waiting
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 100 rows
SELECT
    s_name,
    COUNT(*) AS numwait
FROM sr_mysql.testdb.supplier
JOIN sr_mysql.testdb.lineitem l1 ON s_suppkey = l1.l_suppkey
JOIN sr_mysql.testdb.orders       ON o_orderkey = l1.l_orderkey AND o_orderstatus = 'F'
JOIN sr_mysql.testdb.nation       ON n_nationkey = s_nationkey AND n_name = 'SAUDI ARABIA'
WHERE l1.l_receiptdate > l1.l_commitdate
  AND EXISTS (
      SELECT 1
      FROM sr_mysql.testdb.lineitem l2
      WHERE l2.l_orderkey = l1.l_orderkey
        AND l2.l_suppkey <> l1.l_suppkey
  )
  AND NOT EXISTS (
      SELECT 1
      FROM sr_mysql.testdb.lineitem l3
      WHERE l3.l_orderkey = l1.l_orderkey
        AND l3.l_suppkey <> l1.l_suppkey
        AND l3.l_receiptdate > l3.l_commitdate
  )
GROUP BY s_name
ORDER BY numwait DESC, s_name
LIMIT 100;
