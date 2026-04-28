-- PostgreSQL init: non-TPC-H seed data for test and cross-join tables
-- Preserved from Phase 1 — these tables are NOT replaced by SF1 data.
-- Idempotent: ON CONFLICT DO NOTHING.

-- 3 test_data rows (used by test_postgres.py data tests)
INSERT INTO test_data VALUES
(1, 'Alice', 10.5),
(2, 'Bob', 20.3),
(3, 'Charlie', 30.1)
ON CONFLICT (id) DO NOTHING;

-- 3 departments (used by cross-join tests)
INSERT INTO departments VALUES
(10, 'Engineering'),
(20, 'Marketing'),
(30, 'Sales')
ON CONFLICT (dept_id) DO NOTHING;
