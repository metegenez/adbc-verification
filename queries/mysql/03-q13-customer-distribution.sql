-- TPC-H Q13: Customer Distribution
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 42 rows
SELECT
    c_count,
    COUNT(*) AS custdist
FROM (
    SELECT
        c_custkey,
        COUNT(o_orderkey) AS c_count
    FROM sr_mysql.testdb.customer
    LEFT OUTER JOIN sr_mysql.testdb.orders
        ON c_custkey = o_custkey
        AND o_comment NOT LIKE '%special%requests%'
    GROUP BY c_custkey
) c_orders
GROUP BY c_count
ORDER BY custdist DESC, c_count DESC;
