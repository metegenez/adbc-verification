-- TPC-H Q02: Minimum Cost Supplier
-- Catalog: sr_mysql, Schema: testdb
-- Expected: 100 rows
SELECT
    s_acctbal,
    s_name,
    n_name,
    p_partkey,
    p_mfgr,
    s_address,
    s_phone,
    s_comment
FROM sr_mysql.testdb.part
JOIN sr_mysql.testdb.supplier ON s_nationkey = n_nationkey
JOIN sr_mysql.testdb.partsupp ON ps_partkey = p_partkey AND ps_suppkey = s_suppkey
JOIN sr_mysql.testdb.nation   ON n_nationkey = s_nationkey
JOIN sr_mysql.testdb.region   ON r_regionkey = n_regionkey
WHERE p_size = 15
  AND p_type LIKE '%BRASS'
  AND r_name = 'EUROPE'
  AND ps_supplycost = (
      SELECT MIN(ps_supplycost)
      FROM sr_mysql.testdb.partsupp ps2
      JOIN sr_mysql.testdb.supplier s2 ON ps2.ps_suppkey = s2.s_suppkey
      JOIN sr_mysql.testdb.nation n2   ON s2.s_nationkey = n2.n_nationkey
      JOIN sr_mysql.testdb.region r2   ON n2.n_regionkey = r2.r_regionkey
      WHERE ps2.ps_partkey = p_partkey
        AND r2.r_name = 'EUROPE'
  )
ORDER BY s_acctbal DESC, n_name, s_name, p_partkey
LIMIT 100;
