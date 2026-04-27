-- FlightSQL TPC-H: Join orders with lineitem, count by status
-- Catalog: sr_flightsql, Schema: main
SELECT o.o_orderstatus, COUNT(*) AS cnt
FROM sr_flightsql.main.orders o
JOIN sr_flightsql.main.lineitem l ON o.o_orderkey = l.l_orderkey
GROUP BY o.o_orderstatus
ORDER BY o.o_orderstatus;
