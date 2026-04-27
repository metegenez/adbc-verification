-- PostgreSQL TPC-H: Join orders with lineitem, count by status
-- Catalog: sr_postgres, Schema: public
SELECT o.o_orderstatus, COUNT(*) AS cnt
FROM sr_postgres.public.orders o
JOIN sr_postgres.public.lineitem l ON o.o_orderkey = l.l_orderkey
GROUP BY o.o_orderstatus
ORDER BY o.o_orderstatus;
