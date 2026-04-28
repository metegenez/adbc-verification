-- TPC-H Q09: Product Type Profit Measure
-- Catalog: sr_postgres, Schema: public
-- Expected: 175 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    nation,
    o_year,
    SUM(amount) AS sum_profit
FROM (
    SELECT
        n_name AS nation,
        YEAR(o_orderdate) AS o_year,
        l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity AS amount
    FROM sr_postgres.public.part
    JOIN sr_postgres.public.lineitem  ON p_partkey = l_partkey
    JOIN sr_postgres.public.partsupp  ON ps_partkey = l_partkey AND ps_suppkey = l_suppkey
    JOIN sr_postgres.public.orders    ON o_orderkey = l_orderkey
    JOIN sr_postgres.public.supplier  ON s_suppkey = l_suppkey
    JOIN sr_postgres.public.nation    ON n_nationkey = s_nationkey
    WHERE p_name LIKE '%green%'
) profit
GROUP BY nation, o_year
ORDER BY nation, o_year DESC;
