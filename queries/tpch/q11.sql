-- TPC-H Q11: Important Stock Identification
-- Expected (mysql): 1048 rows
-- Expected (flightsql-starrocks): 1048 rows
SELECT
    ps_partkey,
    SUM(ps_supplycost * ps_availqty) AS value
FROM {catalog}.{db}.partsupp
JOIN {catalog}.{db}.supplier ON s_suppkey = ps_suppkey
JOIN {catalog}.{db}.nation   ON n_nationkey = s_nationkey
WHERE n_name = 'GERMANY'
GROUP BY ps_partkey
HAVING SUM(ps_supplycost * ps_availqty) > (
    SELECT SUM(ps_supplycost * ps_availqty) * 0.0001
    FROM {catalog}.{db}.partsupp ps2
    JOIN {catalog}.{db}.supplier s2 ON s2.s_suppkey = ps2.ps_suppkey
    JOIN {catalog}.{db}.nation n2   ON n2.n_nationkey = s2.s_nationkey
    WHERE n2.n_name = 'GERMANY'
)
ORDER BY value DESC;
