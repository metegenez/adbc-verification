-- TPC-H Q14: Promotion Effect
-- Expected (mysql): 1 rows
-- Expected (flightsql-starrocks): 1 rows
SELECT
    100.00 * SUM(CASE WHEN p_type LIKE 'PROMO%'
                      THEN l_extendedprice * (1 - l_discount)
                      ELSE 0 END)
    / SUM(l_extendedprice * (1 - l_discount)) AS promo_revenue
FROM {catalog}.{db}.lineitem
JOIN {catalog}.{db}.part ON l_partkey = p_partkey
WHERE l_shipdate >= '1995-09-01'
  AND l_shipdate < DATE_ADD('1995-09-01', INTERVAL 1 MONTH);
