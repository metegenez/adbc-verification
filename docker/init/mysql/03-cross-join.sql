-- MySQL init: non-TPC-H seed data for test and cross-join tables
-- Preserved from Phase 1 — these tables are NOT replaced by SF1 data.
-- Idempotent: INSERT IGNORE.

-- 3 test_data rows (used by test_mysql.py data tests)
INSERT IGNORE INTO test_data (id, name, value)
VALUES (1, 'Alice', 10.5), (2, 'Bob', 20.3), (3, 'Charlie', 30.1);

-- 3 departments (used by cross-join tests)
INSERT IGNORE INTO departments (dept_id, dept_name)
VALUES (10, 'Engineering'), (20, 'Marketing'), (30, 'Sales');
