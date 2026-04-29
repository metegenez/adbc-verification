-- TPC-H Q05: Local Supplier Volume
-- Expected (mysql): 5 rows
-- Expected (flightsql-starrocks): 5 rows
SELECT
    n_name,
    SUM(l_extendedprice * (1 - l_discount)) AS revenue
FROM {catalog}.{db}.customer
JOIN {catalog}.{db}.orders   ON c_custkey = o_custkey
JOIN {catalog}.{db}.lineitem ON l_orderkey = o_orderkey
JOIN {catalog}.{db}.supplier ON l_suppkey = s_suppkey AND c_nationkey = s_nationkey
JOIN {catalog}.{db}.nation   ON s_nationkey = n_nationkey
JOIN {catalog}.{db}.region   ON n_regionkey = r_regionkey
WHERE r_name = 'ASIA'
  AND o_orderdate >= '1994-01-01'
  AND o_orderdate < DATE_ADD('1994-01-01', INTERVAL 1 YEAR)
GROUP BY n_name
ORDER BY revenue DESC;
