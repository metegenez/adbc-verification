-- TPC-H Q20: Potential Part Promotion
-- Expected (mysql): 186 rows
-- Expected (flightsql-starrocks): 186 rows
SELECT
    s_name,
    s_address
FROM {catalog}.{db}.supplier
JOIN {catalog}.{db}.nation ON n_nationkey = s_nationkey
WHERE n_name = 'CANADA'
  AND s_suppkey IN (
      SELECT ps_suppkey
      FROM {catalog}.{db}.partsupp
      WHERE ps_partkey IN (
          SELECT p_partkey
          FROM {catalog}.{db}.part
          WHERE p_name LIKE 'forest%'
      )
      AND ps_availqty > (
          SELECT 0.5 * SUM(l_quantity)
          FROM {catalog}.{db}.lineitem
          WHERE l_partkey = ps_partkey
            AND l_suppkey = ps_suppkey
            AND l_shipdate >= '1994-01-01'
            AND l_shipdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
      )
  )
ORDER BY s_name;
