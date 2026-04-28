-- TPC-H Q11: Important Stock Identification
-- Catalog: sr_postgres, Schema: public
-- Expected: 1000 rows
-- Skip: postgres-numeric Arrow extension type unsupported in StarRocks BE (see .planning/phases/02-*/02-NOTES-postgres-numeric.md)
SELECT
    ps_partkey,
    SUM(ps_supplycost * ps_availqty) AS value
FROM sr_postgres.public.partsupp
JOIN sr_postgres.public.supplier ON s_suppkey = ps_suppkey
JOIN sr_postgres.public.nation   ON n_nationkey = s_nationkey
WHERE n_name = 'GERMANY'
GROUP BY ps_partkey
HAVING SUM(ps_supplycost * ps_availqty) > (
    SELECT SUM(ps_supplycost * ps_availqty) * 0.0001
    FROM sr_postgres.public.partsupp ps2
    JOIN sr_postgres.public.supplier s2 ON s2.s_suppkey = ps2.ps_suppkey
    JOIN sr_postgres.public.nation n2   ON n2.n_nationkey = s2.s_nationkey
    WHERE n2.n_name = 'GERMANY'
)
ORDER BY value DESC;
