-- MySQL TPC-H: Select all regions
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 5 rows (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)
SELECT * FROM sr_mysql.testdb.region ORDER BY r_regionkey;
