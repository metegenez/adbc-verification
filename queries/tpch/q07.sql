-- TPC-H Q07: Volume Shipping
-- Expected (mysql): 4 rows
-- Expected (flightsql-starrocks): 4 rows
SELECT
    supp_nation,
    cust_nation,
    l_year,
    SUM(volume) AS revenue
FROM (
    SELECT
        n1.n_name AS supp_nation,
        n2.n_name AS cust_nation,
        YEAR(l_shipdate) AS l_year,
        l_extendedprice * (1 - l_discount) AS volume
    FROM {catalog}.{db}.supplier
    JOIN {catalog}.{db}.lineitem ON s_suppkey = l_suppkey
    JOIN {catalog}.{db}.orders   ON o_orderkey = l_orderkey
    JOIN {catalog}.{db}.customer ON c_custkey = o_custkey
    JOIN {catalog}.{db}.nation n1 ON s_nationkey = n1.n_nationkey
    JOIN {catalog}.{db}.nation n2 ON c_nationkey = n2.n_nationkey
    WHERE (
        (n1.n_name = 'FRANCE' AND n2.n_name = 'GERMANY')
        OR (n1.n_name = 'GERMANY' AND n2.n_name = 'FRANCE')
    )
    AND l_shipdate BETWEEN '1995-01-01' AND '1996-12-31'
) shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year;
