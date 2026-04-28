-- TPC-H Q02: Minimum Cost Supplier
-- Catalog: sr_postgres, Schema: public
-- Expected: 100 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    s.s_acctbal,
    s.s_name,
    n.n_name,
    p.p_partkey,
    p.p_mfgr,
    s.s_address,
    s.s_phone,
    s.s_comment
FROM sr_postgres.public.part p
JOIN sr_postgres.public.partsupp ps ON ps.ps_partkey = p.p_partkey
JOIN sr_postgres.public.supplier s ON s.s_suppkey = ps.ps_suppkey
JOIN sr_postgres.public.nation n ON n.n_nationkey = s.s_nationkey
JOIN sr_postgres.public.region r ON r.r_regionkey = n.n_regionkey
WHERE p.p_size = 15
  AND p.p_type LIKE '%BRASS'
  AND r.r_name = 'EUROPE'
  AND ps.ps_supplycost = (
      SELECT MIN(ps2.ps_supplycost)
      FROM sr_postgres.public.partsupp ps2
      JOIN sr_postgres.public.supplier s2 ON ps2.ps_suppkey = s2.s_suppkey
      JOIN sr_postgres.public.nation n2 ON s2.s_nationkey = n2.n_nationkey
      JOIN sr_postgres.public.region r2 ON n2.n_regionkey = r2.r_regionkey
      WHERE ps2.ps_partkey = p.p_partkey
        AND r2.r_name = 'EUROPE'
  )
ORDER BY s.s_acctbal DESC, n.n_name, s.s_name, p.p_partkey
LIMIT 100;
