-- TPC-H Q22: Global Sales Opportunity
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 0 rows
SELECT
    cntrycode,
    COUNT(*) AS numcust,
    SUM(c_acctbal) AS totacctbal
FROM (
    SELECT
        SUBSTR(c_phone, 1, 2) AS cntrycode,
        c_acctbal
    FROM sr_mysql.testdb.customer
    WHERE SUBSTR(c_phone, 1, 2) IN ('13', '31', '23', '29', '30', '18', '17')
      AND c_acctbal > (
          SELECT AVG(c_acctbal)
          FROM sr_mysql.testdb.customer
          WHERE c_acctbal > 0.00
            AND SUBSTR(c_phone, 1, 2) IN ('13', '31', '23', '29', '30', '18', '17')
      )
      AND NOT EXISTS (
          SELECT 1
          FROM sr_mysql.testdb.orders
          WHERE o_custkey = c_custkey
      )
) custsale
GROUP BY cntrycode
ORDER BY cntrycode;
