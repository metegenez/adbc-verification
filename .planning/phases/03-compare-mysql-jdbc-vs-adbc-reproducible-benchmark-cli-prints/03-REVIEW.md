---
status: findings
phase: 03
phase_name: compare-mysql-jdbc-vs-adbc-reproducible-benchmark-cli-prints
reviewed: 2026-04-28
depth: standard
files_reviewed: 8
findings:
  critical: 0
  warning: 3
  info: 5
  total: 8
---

# Phase 03 Code Review Report

## CR-01 — Exception swallowing in benchmark finally block

- **File:** `benchmark/mysql-jdbc-vs-adbc.py:503-508`
- **Severity:** Warning
- **Description:** The finally block at line 503 calls drop_catalog(conn, JDBC_CATALOG) and drop_catalog(conn, ADBC_CATALOG). If the connection is broken, drop_catalog raises pymysql.err.OperationalError inside a finally block during exception propagation, discarding the original exception and substituting the new one.
- **Fix:** Wrap each drop_catalog call in its own try/except inside the finally clause.

## CR-02 — Latent SQL injection via unescaped catalog_name

- **File:** `lib/catalog_helpers.py:38, 76, 84`
- **Severity:** Warning (latent)
- **Description:** In create_adbc_catalog, create_jdbc_catalog, and drop_catalog, the catalog_name parameter is directly interpolated into SQL without escaping. While all current call sites use hardcoded strings, a future user-supplied input path would be injectable.
- **Fix:** Add an identifier-validity guard: `re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', catalog_name)`.

## CR-03 — Silent data loss when scan-node TotalTime is missing

- **File:** `benchmark/explain_parser.py:101-106`
- **Severity:** Warning
- **Description:** When a scan-node header is matched but no subsequent TotalTime line is found, the node is silently omitted from results with zero indication to the user. This could silently corrupt benchmark data after a StarRocks format change.
- **Fix:** Log a warning to stderr when _NODE_TOTAL.search returns None for a matched scan node.

## CR-04 — Unvalidated int parameter in SQL hint injection

- **File:** `benchmark/explain_parser.py:110-121`
- **Severity:** Info
- **Description:** with_timeout_hint() type-hints timeout_seconds as int but does not validate at runtime. A negative value or non-int would be injected into SQL. Current callers always pass arguments from argparse(type=int).
- **Fix:** Add defensive int coercion and positivity check.

## CR-05 — Duplicate _escape function definition

- **File:** `lib/catalog_helpers.py:34-35, 72-73`
- **Severity:** Info
- **Description:** The identical _escape helper is defined locally inside both create_adbc_catalog and create_jdbc_catalog — pure copy-paste duplication.
- **Fix:** Extract to a module-level private function `_escape_property_value`.

## CR-06 — No checksum verification in JAR download script

- **File:** `docker/fetch-jdbc-jar.sh:27-44`
- **Severity:** Info
- **Description:** The script validates the downloaded JAR only by checking SIZE > 1000000. A corrupted file larger than 1 MB would pass this check. Maven Central publishes SHA1/SHA256 checksums.
- **Fix:** Add SHA1 verification against a pinned checksum.

## CR-07 — Redundant SQL comment stripping in benchmark

- **File:** `benchmark/mysql-jdbc-vs-adbc.py:407, 434`
- **Severity:** Info
- **Description:** _strip_sql_comments() is called twice on the same raw SQL — once in warmup and once in measurement pass.
- **Fix:** Strip comments once during the loading phase and store processed SQL.

## CR-08 — Combined try block hides partial row-count failure

- **File:** `benchmark/mysql-jdbc-vs-adbc.py:468-480`
- **Severity:** Info
- **Description:** Both run_count() calls share a single try/except. If one side fails, the user loses which side failed and what the successful count was.
- **Fix:** Split into two try/except blocks to surface per-catalog row counts.
