-- TPC-H Q17: Small-Quantity-Order Revenue
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 1 rows
SELECT
    SUM(l_extendedprice) / 7.0 AS avg_yearly
FROM sr_mysql.testdb.lineitem
JOIN sr_mysql.testdb.part ON p_partkey = l_partkey
WHERE p_brand = 'Brand#23'
  AND p_container = 'MED BOX'
  AND l_quantity < (
      SELECT 0.2 * AVG(l_quantity)
      FROM sr_mysql.testdb.lineitem l2
      WHERE l2.l_partkey = p_partkey
  );
