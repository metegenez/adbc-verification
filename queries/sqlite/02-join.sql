-- SQLite TPC-H: Join orders with lineitem
-- Catalog: sr_sqlite, Schema: main
-- Count orders per order status
SELECT o.o_orderstatus, COUNT(*) AS cnt
FROM sr_sqlite.main.orders o
JOIN sr_sqlite.main.lineitem l ON o.o_orderkey = l.l_orderkey
GROUP BY o.o_orderstatus
ORDER BY o.o_orderstatus;
