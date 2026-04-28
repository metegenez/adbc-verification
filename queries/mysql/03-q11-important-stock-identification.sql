-- TPC-H Q11: Important Stock Identification
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 1000 rows
SELECT
    ps_partkey,
    SUM(ps_supplycost * ps_availqty) AS value
FROM sr_mysql.testdb.partsupp
JOIN sr_mysql.testdb.supplier ON s_suppkey = ps_suppkey
JOIN sr_mysql.testdb.nation   ON n_nationkey = s_nationkey
WHERE n_name = 'GERMANY'
GROUP BY ps_partkey
HAVING SUM(ps_supplycost * ps_availqty) > (
    SELECT SUM(ps_supplycost * ps_availqty) * 0.0001
    FROM sr_mysql.testdb.partsupp ps2
    JOIN sr_mysql.testdb.supplier s2 ON s2.s_suppkey = ps2.ps_suppkey
    JOIN sr_mysql.testdb.nation n2   ON n2.n_nationkey = s2.s_nationkey
    WHERE n2.n_name = 'GERMANY'
)
ORDER BY value DESC;
