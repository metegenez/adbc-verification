-- MySQL init: departments table for cross-join tests
-- Separate file so 02-data.sql is clean test data only

INSERT IGNORE INTO departments (dept_id, dept_name)
VALUES (10, 'Engineering'), (20, 'Marketing'), (30, 'Sales');
