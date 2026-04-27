-- Cross-driver federation: SQLite employees JOIN PostgreSQL departments
-- Requires catalogs: sr_sqlite (ADBC SQLite driver), sr_postgres (ADBC PostgreSQL driver)
--
-- sr_sqlite.main.employees:    id INTEGER, name TEXT, dept_id INTEGER
-- sr_postgres.public.departments: dept_id INTEGER, dept_name VARCHAR(50)
--
-- Expected: 3 rows (Alice→Engineering, Bob→Marketing, Charlie→Engineering)
SELECT e.name, d.dept_name
FROM sr_sqlite.main.employees e
JOIN sr_postgres.public.departments d ON e.dept_id = d.dept_id
ORDER BY e.name;
