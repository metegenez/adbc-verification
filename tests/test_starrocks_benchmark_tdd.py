"""TDD test for starrocks-jdbc-vs-adbc benchmark module.

This test loads the benchmark script (hyphenated filename) via importlib
and verifies expected constants/attributes before the smoke test in
test_benchmark_cli.py.
"""

from __future__ import annotations

import importlib.util
import pathlib


_HERE = pathlib.Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
_BM_PATH = _PROJECT_ROOT / "benchmark" / "starrocks-jdbc-vs-adbc.py"


def _load_benchmark():
    """Load the benchmark module via importlib (filename contains hyphens)."""
    if not _BM_PATH.exists():
        raise FileNotFoundError(f"Benchmark module not found: {_BM_PATH}")
    spec = importlib.util.spec_from_file_location(
        "starrocks_jdbc_vs_adbc", _BM_PATH
    )
    assert spec is not None, f"Could not create spec for {_BM_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_starrocks_benchmark_module_loads():
    """Verify the benchmark module can be loaded and has expected attributes."""
    bm = _load_benchmark()

    # Check key constants exist
    assert hasattr(bm, "JDBC_CATALOG"), "Missing JDBC_CATALOG"
    assert hasattr(bm, "ADBC_CATALOG"), "Missing ADBC_CATALOG"
    assert bm.JDBC_CATALOG == "bench_jdbc"
    assert bm.ADBC_CATALOG == "bench_adbc"

    # Check ADBC driver is flightsql (not mysql)
    assert "flightsql" in bm.ADBC_DRIVER_PATH, (
        f"Expected flightsql driver, got {bm.ADBC_DRIVER_PATH}"
    )

    # Check JDBC URI targets sr-external
    assert "sr-external" in bm.JDBC_URI, (
        f"Expected sr-external in JDBC_URI, got {bm.JDBC_URI}"
    )

    # Check ADBC URI uses grpc
    assert bm.ADBC_URI.startswith("grpc://"), (
        f"Expected grpc:// URI, got {bm.ADBC_URI}"
    )

    # Check main entry point exists
    assert hasattr(bm, "main"), "Missing main() function"

    # Check rewrite_for_catalog uses "tpch"
    assert hasattr(bm, "rewrite_for_catalog"), "Missing rewrite_for_catalog"
    result = bm.rewrite_for_catalog(
        "SELECT * FROM {catalog}.{db}.lineitem", "test_cat"
    )
    assert "tpch" in result, f"Expected 'tpch' in rewritten SQL, got {result}"
    assert "test_cat" in result
