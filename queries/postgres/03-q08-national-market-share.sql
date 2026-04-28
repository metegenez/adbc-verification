-- TPC-H Q08: National Market Share
-- Catalog: sr_postgres, Schema: public
-- Expected: 2 rows
SELECT
    o_year,
    SUM(CASE WHEN nation = 'BRAZIL' THEN volume ELSE 0 END) / SUM(volume) AS mkt_share
FROM (
    SELECT
        YEAR(o_orderdate) AS o_year,
        l_extendedprice * (1 - l_discount) AS volume,
        n2.n_name AS nation
    FROM sr_postgres.public.part
    JOIN sr_postgres.public.lineitem  ON p_partkey = l_partkey
    JOIN sr_postgres.public.supplier  ON s_suppkey = l_suppkey
    JOIN sr_postgres.public.orders    ON o_orderkey = l_orderkey
    JOIN sr_postgres.public.customer  ON c_custkey = o_custkey
    JOIN sr_postgres.public.nation n1 ON c_nationkey = n1.n_nationkey
    JOIN sr_postgres.public.region    ON r_regionkey = n1.n_regionkey
    JOIN sr_postgres.public.nation n2 ON s_nationkey = n2.n_nationkey
    WHERE r_name = 'AMERICA'
      AND o_orderdate BETWEEN '1995-01-01' AND '1996-12-31'
      AND p_type = 'ECONOMY ANODIZED STEEL'
) all_nations
GROUP BY o_year
ORDER BY o_year;
