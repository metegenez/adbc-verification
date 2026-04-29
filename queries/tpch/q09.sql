-- TPC-H Q09: Product Type Profit Measure
-- Expected (mysql): 175 rows
-- Expected (flightsql-starrocks): 175 rows
SELECT
    nation,
    o_year,
    SUM(amount) AS sum_profit
FROM (
    SELECT
        n_name AS nation,
        YEAR(o_orderdate) AS o_year,
        l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity AS amount
    FROM {catalog}.{db}.part
    JOIN {catalog}.{db}.lineitem  ON p_partkey = l_partkey
    JOIN {catalog}.{db}.partsupp  ON ps_partkey = l_partkey AND ps_suppkey = l_suppkey
    JOIN {catalog}.{db}.orders    ON o_orderkey = l_orderkey
    JOIN {catalog}.{db}.supplier  ON s_suppkey = l_suppkey
    JOIN {catalog}.{db}.nation    ON n_nationkey = s_nationkey
    WHERE p_name LIKE '%green%'
) profit
GROUP BY nation, o_year
ORDER BY nation, o_year DESC;
