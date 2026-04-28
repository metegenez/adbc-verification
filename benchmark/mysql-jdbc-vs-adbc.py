#!/usr/bin/env python3
"""StarRocks MySQL JDBC vs ADBC reproducible benchmark CLI.

Creates separate JDBC (``bench_jdbc``) and ADBC (``bench_adbc``) catalogs against
the same sr-mysql backend, runs matched TPC-H queries against both with
EXPLAIN ANALYZE, parses Summary.TotalTime and per-scan-node times, and prints
a wide ASCII comparison table with AVG and GEOMEAN summary rows.

Catalogs are auto-created at startup and auto-dropped on exit (including on
Ctrl+C and unhandled exceptions). Per-query timeout is enforced server-side
via SET_VAR(query_timeout=...) hint.

Prerequisite: ``docker compose up --build`` with the JAR baked in
(see docker/fetch-jdbc-jar.sh).

Usage:
    .venv/bin/python benchmark/mysql-jdbc-vs-adbc.py
    .venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --queries 1,3,5 --runs 3
    .venv/bin/python benchmark/mysql-jdbc-vs-adbc.py --timeout 120 --queries all

Note: must run under .venv/bin/python (system Python lacks pymysql).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import statistics
import sys

import pymysql

# Ensure project root is on sys.path so `lib` and `benchmark` are importable
# when running as a script from any cwd (mirrors pytest collection behavior).
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from lib.catalog_helpers import (
    create_adbc_catalog,
    create_jdbc_catalog,
    drop_catalog,
    execute_sql,
)
from benchmark.explain_parser import (
    parse_summary_total,
    parse_scan_nodes,
    with_timeout_hint,
)

# ---- Module-level constants ----

PROJECT_ROOT = _PROJECT_ROOT
QUERIES_DIR = _PROJECT_ROOT / "queries" / "mysql"

STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))

MYSQL_USER = "root"
MYSQL_PASS = "testpass"
MYSQL_DB = "testdb"
MYSQL_HOST_INTERNAL = "sr-mysql:3306"

ADBC_DRIVER_PATH = "/opt/starrocks/drivers/libadbc_driver_mysql.so"
ADBC_URI = f"mysql://{MYSQL_USER}:{MYSQL_PASS}@{MYSQL_HOST_INTERNAL}/{MYSQL_DB}"

JDBC_DRIVER_PATH = "/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar"
JDBC_URI = f"jdbc:mysql://{MYSQL_HOST_INTERNAL}/{MYSQL_DB}"
JDBC_DRIVER_CLASS = "com.mysql.cj.jdbc.Driver"

JDBC_CATALOG = "bench_jdbc"
ADBC_CATALOG = "bench_adbc"

_QUERY_FILENAME_RE = re.compile(r"^03-q(\d{2})-")
_SKIP_RE = re.compile(r"--\s*Skip:\s*(.+)")

# Table column definitions: (label, width)
_COLS = [
    ("Query", 5),
    ("JDBC total (ms)", 15),
    ("ADBC total (ms)", 15),
    ("Total ratio", 11),
    ("JDBC scan (ms)", 15),
    ("ADBC scan (ms)", 15),
    ("Scan ratio", 11),
]


# ---- CLI argument parsing ----

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="StarRocks MySQL JDBC vs ADBC benchmark — TPC-H comparison",
    )
    parser.add_argument(
        "--scale",
        default="sf1",
        help="TPC-H scale factor (default: sf1; only sf1 is supported in v1)",
    )
    parser.add_argument(
        "--queries",
        default="all",
        help="Comma-separated TPC-H query numbers (e.g. '1,3,5') or 'all' (default: all)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Measurement runs per query per catalog (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-query timeout in seconds (default: 60)",
    )
    return parser.parse_args()


# ---- Scale validation ----

def validate_scale(scale: str) -> None:
    if scale != "sf1":
        print(
            f"✗ Only --scale sf1 is supported in v1 (got: {scale!r}).",
            file=sys.stderr,
        )
        sys.exit(2)


# ---- Query discovery ----

def discover_queries(queries_arg: str) -> list[tuple[int, pathlib.Path]]:
    """Return [(query_number, path), ...] sorted by query number ascending."""
    requested: set[int] | None
    if queries_arg.lower() == "all":
        requested = None
    else:
        try:
            requested = {int(x.strip()) for x in queries_arg.split(",") if x.strip()}
        except ValueError as e:
            print(f"✗ Invalid --queries value: {queries_arg!r} ({e})", file=sys.stderr)
            sys.exit(2)

    out: list[tuple[int, pathlib.Path]] = []
    for path in sorted(QUERIES_DIR.glob("03-q*.sql")):
        m = _QUERY_FILENAME_RE.match(path.name)
        if not m:
            continue
        qnum = int(m.group(1))
        if requested is not None and qnum not in requested:
            continue
        out.append((qnum, path))

    if not out:
        print(f"✗ No queries matched --queries={queries_arg!r}", file=sys.stderr)
        sys.exit(2)

    return out


# ---- Helpers ----

def _skip_reason(sql: str) -> str | None:
    m = _SKIP_RE.search(sql)
    return m.group(1).strip() if m else None


def _strip_sql_comments(sql: str) -> str:
    """Remove SQL comment lines (lines starting with --)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines).strip()


def rewrite_for_catalog(sql: str, catalog: str) -> str:
    """Replace ``sr_mysql.`` with ``<catalog>.`` so the same SQL runs against
    bench_jdbc and bench_adbc.
    """
    return sql.replace("sr_mysql.", f"{catalog}.")


def run_explain_analyze(conn, sql: str, timeout_seconds: int) -> str:
    """Run 'EXPLAIN ANALYZE <sql with SET_VAR hint>' and return the plan text."""
    hinted = with_timeout_hint(sql, timeout_seconds)
    with conn.cursor() as cur:
        cur.execute("EXPLAIN ANALYZE " + hinted)
        rows = cur.fetchall()
        return "\n".join(row[0] for row in rows) if rows else ""


def run_count(conn, sql: str, timeout_seconds: int) -> int:
    """Run the query and return number of rows. Used for row count comparison."""
    hinted = with_timeout_hint(sql, timeout_seconds)
    with conn.cursor() as cur:
        cur.execute(hinted)
        return len(cur.fetchall())


def fe_alive(conn) -> bool:
    """Probe SELECT 1 to confirm StarRocks FE is responsive after a query error."""
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchall()
        return True
    except Exception:
        return False


# ---- Aggregation ----

def mean_or_none(xs: list[float]) -> float | None:
    return statistics.mean(xs) if xs else None


def geomean_or_none(xs: list[float]) -> float | None:
    cleaned = [x for x in xs if x is not None and x > 0]
    return statistics.geometric_mean(cleaned) if cleaned else None


def aggregate_query_result(
    jdbc_total_runs: list[int | None],
    adbc_total_runs: list[int | None],
    jdbc_scans_runs: list[dict[int, int]],
    adbc_scans_runs: list[dict[int, int]],
) -> dict:
    """Compute per-query JDBC/ADBC total avg, total ratio, scan avg, scan ratio."""
    jdbc_clean = [t for t in jdbc_total_runs if t is not None]
    adbc_clean = [t for t in adbc_total_runs if t is not None]
    jdbc_total_avg_ns = (
        statistics.mean(jdbc_clean) if len(jdbc_clean) == len(jdbc_total_runs) else None
    )
    adbc_total_avg_ns = (
        statistics.mean(adbc_clean) if len(adbc_clean) == len(adbc_total_runs) else None
    )
    total_ratio = (
        jdbc_total_avg_ns / adbc_total_avg_ns
        if jdbc_total_avg_ns is not None
        and adbc_total_avg_ns is not None
        and adbc_total_avg_ns > 0
        else None
    )

    # Scan ratios: common operator IDs across both catalogs
    common_ids = (
        set.intersection(*(set(d) for d in jdbc_scans_runs))
        if jdbc_scans_runs and all(jdbc_scans_runs)
        else set()
    ) & (
        set.intersection(*(set(d) for d in adbc_scans_runs))
        if adbc_scans_runs and all(adbc_scans_runs)
        else set()
    )
    per_id_ratios: list[float] = []
    jdbc_scan_avg_ns_list: list[float] = []
    adbc_scan_avg_ns_list: list[float] = []
    for op_id in common_ids:
        jdbc_avg = statistics.mean(d[op_id] for d in jdbc_scans_runs)
        adbc_avg = statistics.mean(d[op_id] for d in adbc_scans_runs)
        jdbc_scan_avg_ns_list.append(jdbc_avg)
        adbc_scan_avg_ns_list.append(adbc_avg)
        if adbc_avg > 0:
            per_id_ratios.append(jdbc_avg / adbc_avg)
    scan_ratio = statistics.mean(per_id_ratios) if per_id_ratios else None
    jdbc_scan_avg_ns = (
        statistics.mean(jdbc_scan_avg_ns_list) if jdbc_scan_avg_ns_list else None
    )
    adbc_scan_avg_ns = (
        statistics.mean(adbc_scan_avg_ns_list) if adbc_scan_avg_ns_list else None
    )

    return {
        "jdbc_total_ms": jdbc_total_avg_ns / 1e6 if jdbc_total_avg_ns else None,
        "adbc_total_ms": adbc_total_avg_ns / 1e6 if adbc_total_avg_ns else None,
        "total_ratio": total_ratio,
        "jdbc_scan_ms": jdbc_scan_avg_ns / 1e6 if jdbc_scan_avg_ns else None,
        "adbc_scan_ms": adbc_scan_avg_ns / 1e6 if adbc_scan_avg_ns else None,
        "scan_ratio": scan_ratio,
    }


# ---- ASCII table rendering ----

def _fmt(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{decimals}f}"


def render_table(per_query_rows: dict[int, dict], summary: dict) -> str:
    """Render the wide ASCII table with AVG/GEOM summary rows."""
    sep = "+" + "+".join("-" * (w + 2) for _, w in _COLS) + "+"

    def _format_data_row(label: str, row: dict) -> str:
        cells = [
            f"{label:<{_COLS[0][1]}}",
            f"{_fmt(row['jdbc_total_ms']):>{_COLS[1][1]}}",
            f"{_fmt(row['adbc_total_ms']):>{_COLS[2][1]}}",
            f"{_fmt(row['total_ratio'], 2):>{_COLS[3][1]}}",
            f"{_fmt(row['jdbc_scan_ms']):>{_COLS[4][1]}}",
            f"{_fmt(row['adbc_scan_ms']):>{_COLS[5][1]}}",
            f"{_fmt(row['scan_ratio'], 2):>{_COLS[6][1]}}",
        ]
        return "| " + " | ".join(cells) + " |"

    lines = [sep]
    header = "| " + " | ".join(f"{lbl:<{w}}" for lbl, w in _COLS) + " |"
    lines.append(header)
    lines.append(sep)
    for qnum in sorted(per_query_rows.keys()):
        lines.append(_format_data_row(f"Q{qnum:02d}", per_query_rows[qnum]))
    lines.append(sep)
    lines.append(_format_data_row("AVG", summary["avg"]))
    lines.append(_format_data_row("GEOM", summary["geom"]))
    lines.append(sep)
    return "\n".join(lines)


# ---- Summary aggregation ----

def compute_summary(per_query_rows: dict[int, dict]) -> dict:
    """Compute AVG and GEOM summary rows across all queries."""

    def _collect(key: str) -> list[float]:
        return [r[key] for r in per_query_rows.values() if r.get(key) is not None]

    def _agg(fn, key: str) -> float | None:
        vals = _collect(key)
        if not vals:
            return None
        try:
            return fn(vals)
        except statistics.StatisticsError:
            return None

    avg = {
        "jdbc_total_ms": _agg(statistics.mean, "jdbc_total_ms"),
        "adbc_total_ms": _agg(statistics.mean, "adbc_total_ms"),
        "total_ratio": _agg(statistics.mean, "total_ratio"),
        "jdbc_scan_ms": _agg(statistics.mean, "jdbc_scan_ms"),
        "adbc_scan_ms": _agg(statistics.mean, "adbc_scan_ms"),
        "scan_ratio": _agg(statistics.mean, "scan_ratio"),
    }
    geom = {
        "jdbc_total_ms": _agg(statistics.geometric_mean, "jdbc_total_ms"),
        "adbc_total_ms": _agg(statistics.geometric_mean, "adbc_total_ms"),
        "total_ratio": _agg(statistics.geometric_mean, "total_ratio"),
        "jdbc_scan_ms": _agg(statistics.geometric_mean, "jdbc_scan_ms"),
        "adbc_scan_ms": _agg(statistics.geometric_mean, "adbc_scan_ms"),
        "scan_ratio": _agg(statistics.geometric_mean, "scan_ratio"),
    }
    return {"avg": avg, "geom": geom}


# ---- Main benchmark runner ----

def run_benchmark(args: argparse.Namespace) -> bool:
    validate_scale(args.scale)
    queries = discover_queries(args.queries)

    print(f"◆ Connecting to StarRocks at {STARROCKS_HOST}:{STARROCKS_PORT}...")
    conn = pymysql.connect(
        host=STARROCKS_HOST,
        port=STARROCKS_PORT,
        user="root",
        password="",
        autocommit=True,
    )

    try:
        drop_catalog(conn, JDBC_CATALOG)
        drop_catalog(conn, ADBC_CATALOG)

        print(f"◆ Creating JDBC catalog '{JDBC_CATALOG}' (driver={JDBC_DRIVER_PATH})...")
        create_jdbc_catalog(
            conn,
            catalog_name=JDBC_CATALOG,
            jdbc_uri=JDBC_URI,
            user=MYSQL_USER,
            password=MYSQL_PASS,
            driver_url=JDBC_DRIVER_PATH,
            driver_class=JDBC_DRIVER_CLASS,
        )

        print(f"◆ Creating ADBC catalog '{ADBC_CATALOG}' (driver={ADBC_DRIVER_PATH})...")
        create_adbc_catalog(
            conn,
            catalog_name=ADBC_CATALOG,
            driver_url=ADBC_DRIVER_PATH,
            uri=ADBC_URI,
        )

        # Read & filter queries
        loaded: list[tuple[int, str]] = []
        for qnum, path in queries:
            raw = path.read_text()
            sr = _skip_reason(raw)
            if sr:
                print(f"  ⊘ Q{qnum:02d}: skipped ({sr})", file=sys.stderr)
                continue
            loaded.append((qnum, raw))

        if not loaded:
            print("✗ All requested queries are skipped", file=sys.stderr)
            return False

        # Warm-up phase
        print(f"◆ Warmup: {len(loaded)} queries × 2 catalogs (one pass each)...")
        for qnum, raw in loaded:
            for catalog in (JDBC_CATALOG, ADBC_CATALOG):
                sql = rewrite_for_catalog(_strip_sql_comments(raw), catalog)
                try:
                    run_explain_analyze(conn, sql, args.timeout)
                except Exception as e:
                    print(
                        f"  ! Q{qnum:02d} warmup on {catalog} failed: {e}",
                        file=sys.stderr,
                    )
                    if not fe_alive(conn):
                        print(
                            "✗ StarRocks FE is unresponsive. Run "
                            "`docker compose -f docker/docker-compose.yml restart sr-main`",
                            file=sys.stderr,
                        )
                        return False

        # Measurement phase
        print(
            f"◆ Measurement: {len(loaded)} queries × {args.runs} runs × 2 catalogs..."
        )
        per_query_rows: dict[int, dict] = {}
        for qnum, raw in loaded:
            jdbc_totals: list[int | None] = []
            adbc_totals: list[int | None] = []
            jdbc_scans: list[dict[int, int]] = []
            adbc_scans: list[dict[int, int]] = []

            sql = _strip_sql_comments(raw)
            jdbc_sql = rewrite_for_catalog(sql, JDBC_CATALOG)
            adbc_sql = rewrite_for_catalog(sql, ADBC_CATALOG)

            for _ in range(args.runs):
                # JDBC run
                try:
                    plan = run_explain_analyze(conn, jdbc_sql, args.timeout)
                    jdbc_totals.append(parse_summary_total(plan))
                    jdbc_scans.append(parse_scan_nodes(plan))
                except Exception as e:
                    print(f"  ! Q{qnum:02d} JDBC failed: {e}", file=sys.stderr)
                    jdbc_totals.append(None)
                    jdbc_scans.append({})
                    if not fe_alive(conn):
                        print("✗ FE down — abort", file=sys.stderr)
                        return False
                # ADBC run
                try:
                    plan = run_explain_analyze(conn, adbc_sql, args.timeout)
                    adbc_totals.append(parse_summary_total(plan))
                    adbc_scans.append(parse_scan_nodes(plan))
                except Exception as e:
                    print(f"  ! Q{qnum:02d} ADBC failed: {e}", file=sys.stderr)
                    adbc_totals.append(None)
                    adbc_scans.append({})
                    if not fe_alive(conn):
                        print("✗ FE down — abort", file=sys.stderr)
                        return False

            # Row count check — once per query
            if any(t is not None for t in jdbc_totals) and any(
                t is not None for t in adbc_totals
            ):
                try:
                    jdbc_n = run_count(conn, jdbc_sql, args.timeout)
                    adbc_n = run_count(conn, adbc_sql, args.timeout)
                    if jdbc_n != adbc_n:
                        print(
                            f"  ! Q{qnum:02d} row count mismatch: JDBC={jdbc_n} ADBC={adbc_n}",
                            file=sys.stderr,
                        )
                except Exception as e:
                    print(
                        f"  ! Q{qnum:02d} row count check skipped: {e}",
                        file=sys.stderr,
                    )

            per_query_rows[qnum] = aggregate_query_result(
                jdbc_totals, adbc_totals, jdbc_scans, adbc_scans
            )
            print(f"  ✓ Q{qnum:02d} done")

        summary = compute_summary(per_query_rows)

        print()
        print(
            "═══════════════════════════════════════════════════════════════════════════════════════════"
        )
        print(" MySQL JDBC vs ADBC Benchmark")
        print(
            f" Scale: {args.scale} | Queries: {len(loaded)} | Runs: {args.runs} (+1 warmup) | Timeout: {args.timeout}s"
        )
        print(
            "═══════════════════════════════════════════════════════════════════════════════════════════"
        )
        print(render_table(per_query_rows, summary))
        return True

    finally:
        try:
            drop_catalog(conn, JDBC_CATALOG)
            drop_catalog(conn, ADBC_CATALOG)
        finally:
            conn.close()


def main() -> None:
    args = parse_args()
    try:
        sys.exit(0 if run_benchmark(args) else 1)
    except KeyboardInterrupt:
        print(
            "\nInterrupted — catalogs dropped via finally clause", file=sys.stderr
        )
        sys.exit(130)
    except pymysql.err.OperationalError as e:
        print(f"\n✗ StarRocks connection error: {e}", file=sys.stderr)
        print(
            "If FE crashed, run: docker compose -f docker/docker-compose.yml restart sr-main",
            file=sys.stderr,
        )
        sys.exit(2)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
