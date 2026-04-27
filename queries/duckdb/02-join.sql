-- DuckDB TPC-H: Join orders with lineitem, count by status
-- Catalog: sr_duckdb, Schema: main
SELECT o.o_orderstatus, COUNT(*) AS cnt
FROM sr_duckdb.main.orders o
JOIN sr_duckdb.main.lineitem l ON o.o_orderkey = l.l_orderkey
GROUP BY o.o_orderstatus
ORDER BY o.o_orderstatus;
