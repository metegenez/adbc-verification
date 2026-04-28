"""EXPLAIN ANALYZE text parsers for the MySQL JDBC vs ADBC benchmark CLI.

Parses StarRocks EXPLAIN ANALYZE output (verified live against sr-main on
2026-04-28; see .planning/phases/03-*/03-RESEARCH.md "EXPLAIN ANALYZE Format
(Verified Live)" for the canonical format).

Public API:
    parse_duration_ns(s)     -> int      # "8s544ms" -> 8_544_000_000
    parse_summary_total(t)   -> int      # Summary.TotalTime in nanoseconds
    parse_scan_nodes(t)      -> dict     # {operator_id: total_ns} for all scans
    with_timeout_hint(sql,n) -> str      # inject SET_VAR(query_timeout=n) hint

All parsers strip ANSI color codes before matching (StarRocks FE colors
high-latency nodes red and medium-latency salmon; pymysql passes the bytes
through unchanged).

Per D-26, parser failures are tool bugs — ``parse_summary_total`` raises
ValueError on no match rather than returning None or 0. Callers must surface
the failure (the CLI's --help should document this contract).
"""

from __future__ import annotations

import re

# ---- Regex constants (module-private; verified against live container) ----

# Strip ANSI escape sequences from EXPLAIN ANALYZE output.
_ANSI = re.compile(r'\x1b\[[0-9;]*m')

# Duration grammar: concatenated segments, e.g. "8s544ms", "419.099us", "0ns".
_DUR_SEG = re.compile(r'(\d+(?:\.\d+)?)\s*(s|ms|us|ns)')
_UNIT_NS = {"s": 1_000_000_000, "ms": 1_000_000, "us": 1_000, "ns": 1}

# Summary.TotalTime line: appears at top-level under "Summary" header,
# does NOT carry a "(NN.NN%)" suffix.
_SUMMARY_TOTAL = re.compile(r'^\s*TotalTime:\s*(\S+)\s*$', re.MULTILINE)

# Scan-node header. Tolerant to all four candidate labels — the live JDBC
# label is not yet observed (RESEARCH.md §A3) so the parser accepts any of
# ADBC_SCAN, JDBC_SCAN, JDBCScanNode, MysqlScanNode.
_SCAN_NODE = re.compile(
    r'(?P<scan>ADBC_SCAN|JDBC_SCAN|JDBCScanNode|MysqlScanNode)\s*\(id=(?P<id>\d+)\)'
)

# Per-node TotalTime line: carries a "(NN.NN%)" suffix and may include
# bracketed CPUTime/ScanTime details. The `\(\d` anchor distinguishes this
# from the Summary-level TotalTime which has no parenthesized suffix.
_NODE_TOTAL = re.compile(r'TotalTime:\s*(?P<dur>\S+)\s*\(\d', re.MULTILINE)

# SET_VAR injection target: first SELECT keyword in the SQL.
_SELECT_PREFIX = re.compile(r'^\s*SELECT\b', re.IGNORECASE)


# ---- Public API ----

def parse_duration_ns(s: str) -> int:
    """Parse a StarRocks duration string to nanoseconds.

    Handles concatenated segments: ``8s544ms`` -> 8_544_000_000,
    ``419.099us`` -> 419_099, ``0ns`` -> 0. Returns 0 if no segment
    matches (which should not happen for valid plan output).
    """
    total_ns = 0.0
    for m in _DUR_SEG.finditer(s):
        total_ns += float(m.group(1)) * _UNIT_NS[m.group(2)]
    return int(total_ns)


def parse_summary_total(plan_text: str) -> int:
    """Return ``Summary.TotalTime`` in nanoseconds.

    Raises ``ValueError`` per D-26 if the line is not found — the parser
    is the verification mechanism; failure must surface, not silently
    return 0.
    """
    plan = _ANSI.sub('', plan_text)
    m = _SUMMARY_TOTAL.search(plan)
    if not m:
        raise ValueError(
            "EXPLAIN ANALYZE output does not contain a Summary.TotalTime "
            "line — the StarRocks plan format may have changed."
        )
    return parse_duration_ns(m.group(1))


def parse_scan_nodes(plan_text: str) -> dict[int, int]:
    """Return ``{operator_id: total_ns}`` for every scan node in the plan.

    Matching key is ``id=N`` (per D-08). The regex tolerates ADBC_SCAN,
    JDBC_SCAN, JDBCScanNode, and MysqlScanNode labels. For each scan-node
    header, the function takes the FIRST per-node ``TotalTime: ... (NN%)``
    line that appears after the header — that is the node's own time
    (subsequent TotalTime lines belong to subordinate operators).

    Returns an empty dict if the plan contains no scan nodes — callers
    must decide whether that's an error for their query.
    """
    plan = _ANSI.sub('', plan_text)
    out: dict[int, int] = {}
    for m in _SCAN_NODE.finditer(plan):
        op_id = int(m.group("id"))
        rest = plan[m.end():]
        t = _NODE_TOTAL.search(rest)
        if t:
            out[op_id] = parse_duration_ns(t.group("dur"))
    return out


def with_timeout_hint(sql: str, timeout_seconds: int) -> str:
    """Inject ``SET_VAR(query_timeout = N)`` after the first SELECT keyword.

    All 22 TPC-H queries in ``queries/mysql/`` begin with ``SELECT`` (no
    WITH/CTE prefix), so a single substitution suffices. The result is
    parsed by StarRocks as ``SELECT /*+ SET_VAR(query_timeout = N) */ ...``
    which enforces server-side timeout (D-19, RESEARCH.md §6).
    """
    return _SELECT_PREFIX.sub(
        f'SELECT /*+ SET_VAR(query_timeout = {timeout_seconds}) */',
        sql,
        count=1,
    )
