-- TPC-H Q22: Global Sales Opportunity
-- Expected (mysql): 7 rows
-- Expected (flightsql-starrocks): 7 rows
SELECT
    cntrycode,
    COUNT(*) AS numcust,
    SUM(c_acctbal) AS totacctbal
FROM (
    SELECT
        SUBSTR(c_phone, 1, 2) AS cntrycode,
        c_acctbal
    FROM {catalog}.{db}.customer
    WHERE SUBSTR(c_phone, 1, 2) IN ('13', '31', '23', '29', '30', '18', '17')
      AND c_acctbal > (
          SELECT AVG(c_acctbal)
          FROM {catalog}.{db}.customer
          WHERE c_acctbal > 0.00
            AND SUBSTR(c_phone, 1, 2) IN ('13', '31', '23', '29', '30', '18', '17')
      )
      AND NOT EXISTS (
          SELECT 1
          FROM {catalog}.{db}.orders
          WHERE o_custkey = c_custkey
      )
) custsale
GROUP BY cntrycode
ORDER BY cntrycode;
