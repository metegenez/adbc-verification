-- MySQL TPC-H: Join orders with lineitem, count by status
-- Catalog: sr_mysql, Schema: testdb
SELECT o.o_orderstatus, COUNT(*) AS cnt
FROM sr_mysql.testdb.orders o
JOIN sr_mysql.testdb.lineitem l ON o.o_orderkey = l.l_orderkey
GROUP BY o.o_orderstatus
ORDER BY o.o_orderstatus;
