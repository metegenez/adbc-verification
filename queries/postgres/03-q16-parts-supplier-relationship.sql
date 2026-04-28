-- TPC-H Q16: Parts/Supplier Relationship
-- Catalog: sr_postgres, Schema: public
-- Expected: 16630 rows
SELECT
    p_brand,
    p_type,
    p_size,
    COUNT(DISTINCT ps_suppkey) AS supplier_cnt
FROM sr_postgres.public.partsupp
JOIN sr_postgres.public.part ON p_partkey = ps_partkey
WHERE p_brand <> 'Brand#45'
  AND p_type NOT LIKE 'MEDIUM POLISHED%'
  AND p_size IN (49, 14, 23, 45, 19, 3, 36, 9)
  AND ps_suppkey NOT IN (
      SELECT s_suppkey
      FROM sr_postgres.public.supplier
      WHERE s_comment LIKE '%Customer%Complaints%'
  )
GROUP BY p_brand, p_type, p_size
ORDER BY supplier_cnt DESC, p_brand, p_type, p_size;
