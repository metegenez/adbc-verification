-- TPC-H Q15: Top Supplier
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 1 rows
WITH revenue AS (
    SELECT
        l_suppkey AS supplier_no,
        SUM(l_extendedprice * (1 - l_discount)) AS total_revenue
    FROM sr_mysql.testdb.lineitem
    WHERE l_shipdate >= '1996-01-01'
      AND l_shipdate < DATE_ADD('1996-01-01', INTERVAL 3 MONTH)
    GROUP BY l_suppkey
)
SELECT
    s_suppkey,
    s_name,
    s_address,
    s_phone,
    total_revenue
FROM sr_mysql.testdb.supplier
JOIN revenue ON s_suppkey = supplier_no
WHERE total_revenue = (SELECT MAX(total_revenue) FROM revenue)
ORDER BY s_suppkey;
