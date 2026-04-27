-- PostgreSQL TPC-H: Select all regions
-- Catalog: sr_postgres, Schema: public
-- Expected: 5 rows (AFRICA, AMERICA, ASIA, EUROPE, MIDDLE EAST)
SELECT * FROM sr_postgres.public.region ORDER BY r_regionkey;
