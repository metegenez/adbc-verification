"""Smoke tests for the JDBC vs ADBC benchmark CLI.

Verifies (1) the create_jdbc_catalog helper produces a working catalog,
(2) the explain_parser correctly extracts Summary.TotalTime from a real
EXPLAIN ANALYZE response, and (3) the CLI runs end-to-end on a single
query with --runs 1 and exits 0.

Marker: @pytest.mark.benchmark — run with ``.venv/bin/pytest -m benchmark``.

Prerequisite: the StarRocks Docker stack must be up with the JDBC JAR
baked in (run ``bash docker/fetch-jdbc-jar.sh && docker compose -f
docker/docker-compose.yml up --build -d``).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from lib.catalog_helpers import (
    create_adbc_catalog,
    create_jdbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)
from benchmark.explain_parser import parse_summary_total, parse_scan_nodes

_MYSQL_USER = "root"
_MYSQL_PASS = "testpass"
_MYSQL_DB = "testdb"
_JDBC_DRIVER_PATH = "file:///opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"
_JDBC_URI = f"jdbc:mysql://sr-mysql:3306"
_ADBC_DRIVER_PATH = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
_ADBC_URI = f"mysql://{_MYSQL_USER}:{_MYSQL_PASS}@sr-mysql:3306/{_MYSQL_DB}"

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CLI_PATH = _PROJECT_ROOT / "benchmark" / "mysql-jdbc-vs-adbc.py"


@pytest.mark.benchmark
def test_create_jdbc_catalog_lifecycle(sr_conn):
    """create_jdbc_catalog produces a catalog visible in SHOW CATALOGS."""
    cat = "test_bench_jdbc_lc"
    try:
        drop_catalog(sr_conn, cat)
        create_jdbc_catalog(
            sr_conn,
            catalog_name=cat,
            jdbc_uri=_JDBC_URI,
            user=_MYSQL_USER,
            password=_MYSQL_PASS,
            driver_url=_JDBC_DRIVER_PATH,
        )
        assert cat in show_catalogs(sr_conn), (
            f"'{cat}' missing from {show_catalogs(sr_conn)}"
        )

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        db_names = [row[0] for row in dbs]
        assert _MYSQL_DB in db_names, f"Expected '{_MYSQL_DB}' in {db_names}"
    finally:
        drop_catalog(sr_conn, cat)


@pytest.mark.benchmark
def test_explain_analyze_parser_extracts_total_for_q01(sr_conn):
    """Run EXPLAIN ANALYZE for TPC-H Q01 through an ADBC bench catalog and
    verify the parser returns a non-zero Summary.TotalTime in nanoseconds.
    """
    cat = "test_bench_parser_q01"
    try:
        drop_catalog(sr_conn, cat)
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=_ADBC_DRIVER_PATH,
            uri=_ADBC_URI,
        )
        q01_path = _PROJECT_ROOT / "queries" / "tpch" / "q01.sql"
        raw = q01_path.read_text()
        sql_lines = [ln for ln in raw.splitlines() if not ln.strip().startswith("--")]
        sql = "\n".join(sql_lines).strip().rstrip(";")
        sql = sql.replace("{catalog}", cat).replace("{db}", "testdb")

        with sr_conn.cursor() as cur:
            cur.execute("EXPLAIN ANALYZE " + sql)
            rows = cur.fetchall()
            plan_text = "\n".join(r[0] for r in rows)

        total_ns = parse_summary_total(plan_text)
        assert total_ns > 0, f"parse_summary_total returned {total_ns}"
        scans = parse_scan_nodes(plan_text)
        assert len(scans) >= 1, f"Expected at least one scan node, got {scans}"
    finally:
        drop_catalog(sr_conn, cat)


@pytest.mark.benchmark
def test_benchmark_cli_smoke_runs_one_query():
    """Invoke the CLI with --queries 1 --runs 1 and assert it exits 0 with
    expected table headers in stdout.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(_CLI_PATH),
            "--queries", "1",
            "--runs", "1",
            "--timeout", "120",
        ],
        capture_output=True,
        text=True,
        cwd=_PROJECT_ROOT,
        timeout=600,
    )

    if result.returncode != 0:
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    assert result.returncode == 0, (
        f"CLI exited {result.returncode}\n"
        f"STDOUT: {result.stdout}\n"
        f"STDERR: {result.stderr}"
    )
    assert "JDBC total (ms)" in result.stdout
    assert "ADBC total (ms)" in result.stdout
    assert "Total ratio" in result.stdout
    assert "Q01" in result.stdout
    assert "AVG" in result.stdout
    assert "GEOM" in result.stdout
