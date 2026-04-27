-- SQLite TPC-H: Select all regions
-- Catalog: sr_sqlite, Schema: main
-- Expected: 5 rows (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)
SELECT * FROM sr_sqlite.main.region ORDER BY r_regionkey;
