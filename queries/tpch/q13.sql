-- TPC-H Q13: Customer Distribution
-- Expected: 42 rows
SELECT
    c_count,
    COUNT(*) AS custdist
FROM (
    SELECT
        c_custkey,
        COUNT(o_orderkey) AS c_count
    FROM {catalog}.{db}.customer
    LEFT OUTER JOIN {catalog}.{db}.orders
        ON c_custkey = o_custkey
        AND o_comment NOT LIKE '%special%requests%'
    GROUP BY c_custkey
) c_orders
GROUP BY c_count
ORDER BY custdist DESC, c_count DESC;
