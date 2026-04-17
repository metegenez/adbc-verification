"""Session-scoped pytest fixtures for StarRocks ADBC verification suite."""

from __future__ import annotations

import pytest

from lib.starrocks import ensure_starrocks_running, tail_log
from lib.docker_backends import (
    ensure_sqlflite_running,
    ensure_mysql_running,
    ensure_postgres_running,
    stop_container,
)
from lib.driver_registry import get_driver_path
from lib.tls import start_sqlflite_tls


# ---------------------------------------------------------------------------
# pytest hook: store per-phase report on the test item so the
# capture_on_failure fixture can inspect request.node.rep_call.
# ---------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ---------------------------------------------------------------------------
# StarRocks connection (session-scoped, no teardown -- per D-03)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sr_conn():
    """Start StarRocks FE/BE if needed and return a pymysql connection."""
    conn = ensure_starrocks_running()
    yield conn
    # D-03: leave FE/BE running; no teardown.


# ---------------------------------------------------------------------------
# Driver paths (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sqlite_driver_path() -> str:
    return get_driver_path("sqlite")


@pytest.fixture(scope="session")
def flightsql_driver_path() -> str:
    return get_driver_path("flightsql")


@pytest.fixture(scope="session")
def postgres_driver_path() -> str:
    return get_driver_path("postgresql")


@pytest.fixture(scope="session")
def duckdb_driver_path() -> str:
    return get_driver_path("duckdb")


@pytest.fixture(scope="session")
def mysql_driver_path() -> str:
    return get_driver_path("mysql")


# ---------------------------------------------------------------------------
# Docker backends (session-scoped with teardown)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mysql_port():
    """Start MySQL and yield port 3306.  Teardown stops container."""
    port = ensure_mysql_running()
    yield port
    stop_container("adbc_test_mysql")


@pytest.fixture(scope="session")
def sqlflite_port():
    """Start sqlflite (no TLS) and yield port 31337.  Teardown stops container."""
    port = ensure_sqlflite_running()
    yield port
    stop_container("adbc_test_sqlflite")


@pytest.fixture(scope="session")
def postgres_port():
    """Start PostgreSQL and yield port 5432.  Teardown stops container."""
    port = ensure_postgres_running()
    yield port
    stop_container("adbc_test_postgres")


@pytest.fixture(scope="session")
def sqlflite_tls():
    """Start sqlflite with TLS and yield ``(port, ca_cert_path)``.

    Teardown stops container.
    """
    port, ca_cert_path = start_sqlflite_tls()
    yield (port, ca_cert_path)
    stop_container("adbc_test_sqlflite_tls")


# ---------------------------------------------------------------------------
# Structured failure capture (autouse -- per D-12)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def capture_on_failure(request):
    """On test failure, attach FE and BE log tails to user_properties."""
    yield
    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is not None and rep_call.failed:
        fe_tail = tail_log("fe", n=50)
        be_tail = tail_log("be", n=50)
        request.node.user_properties.append(("fe_log_tail", fe_tail))
        request.node.user_properties.append(("be_log_tail", be_tail))
