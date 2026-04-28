-- TPC-H Q09: Product Type Profit Measure
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 175 rows
SELECT
    nation,
    o_year,
    SUM(amount) AS sum_profit
FROM (
    SELECT
        n_name AS nation,
        YEAR(o_orderdate) AS o_year,
        l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity AS amount
    FROM sr_mysql.testdb.part
    JOIN sr_mysql.testdb.lineitem  ON p_partkey = l_partkey
    JOIN sr_mysql.testdb.partsupp  ON ps_partkey = l_partkey AND ps_suppkey = l_suppkey
    JOIN sr_mysql.testdb.orders    ON o_orderkey = l_orderkey
    JOIN sr_mysql.testdb.supplier  ON s_suppkey = l_suppkey
    JOIN sr_mysql.testdb.nation    ON n_nationkey = s_nationkey
    WHERE p_name LIKE '%green%'
) profit
GROUP BY nation, o_year
ORDER BY nation, o_year DESC;
