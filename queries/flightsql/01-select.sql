-- FlightSQL TPC-H: Select all regions
-- Catalog: sr_flightsql, Schema: main
-- Expected: 5 rows (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)
SELECT * FROM sr_flightsql.main.region ORDER BY r_regionkey;
