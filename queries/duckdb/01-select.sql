-- DuckDB TPC-H: Select all regions
-- Catalog: sr_duckdb, Schema: main
-- Expected: 5 rows (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)
SELECT * FROM sr_duckdb.main.region ORDER BY r_regionkey;
