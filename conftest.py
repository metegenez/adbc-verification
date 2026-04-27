"""Session-scoped pytest fixtures for StarRocks ADBC verification suite.

Docker Compose mode: StarRocks and all backends run in containers managed
by ``docker compose``. Drivers are at fixed paths inside the StarRocks
container image. Backend port fixtures return service-internal port
constants; URIs use Docker DNS service names.
"""

from __future__ import annotations

import os
import subprocess

import pymysql
import pytest

# ---------------------------------------------------------------------------
# Host → StarRocks connection settings
# ---------------------------------------------------------------------------

STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))

# ---------------------------------------------------------------------------
# Container-internal ADBC driver paths (baked into StarRocks image)
# ---------------------------------------------------------------------------

SQLITE_DRIVER = "/opt/starrocks/drivers/libadbc_driver_sqlite.so"
POSTGRES_DRIVER = "/opt/starrocks/drivers/libadbc_driver_postgresql.so"
FLIGHTSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_flightsql.so"
DUCKDB_DRIVER = "/opt/starrocks/drivers/libadbc_driver_duckdb.so"
MYSQL_DRIVER = "/opt/starrocks/drivers/libadbc_driver_mysql.so"

# ---------------------------------------------------------------------------
# Container-internal data file paths (pre-baked, copied by Dockerfile)
# ---------------------------------------------------------------------------

SQLITE_TEST_DB = "/opt/starrocks/data/test_sqlite.db"
CROSS_SQLITE_A_DB = "/opt/starrocks/data/cross_sqlite_a.db"
CROSS_SQLITE_B_DB = "/opt/starrocks/data/cross_sqlite_b.db"
DUCKDB_TPCH_DB = "/opt/starrocks/data/tpch_duckdb.db"

# ---------------------------------------------------------------------------
# TLS certificate paths (pre-generated in docker/certs/, accessed from host)
# ---------------------------------------------------------------------------

FLIGHTSQL_CA_CERT = os.environ.get(
    "FLIGHTSQL_CA_CERT",
    os.path.join(os.path.dirname(__file__), "docker", "certs", "flightsql-ca.pem"),
)
POSTGRES_CA_CERT = os.environ.get(
    "POSTGRES_CA_CERT",
    os.path.join(os.path.dirname(__file__), "docker", "certs", "postgres-ca.pem"),
)


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
# StarRocks connection (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sr_conn():
    """Connect to StarRocks FE via STARROCKS_HOST:STARROCKS_PORT."""
    conn = pymysql.connect(
        host=STARROCKS_HOST,
        port=STARROCKS_PORT,
        user="root",
        password="",
        autocommit=True,
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Driver path fixtures (session-scoped, fixed container-internal paths)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sqlite_driver_path() -> str:
    return SQLITE_DRIVER


@pytest.fixture(scope="session")
def flightsql_driver_path() -> str:
    return FLIGHTSQL_DRIVER


@pytest.fixture(scope="session")
def postgres_driver_path() -> str:
    return POSTGRES_DRIVER


@pytest.fixture(scope="session")
def duckdb_driver_path() -> str:
    return DUCKDB_DRIVER


@pytest.fixture(scope="session")
def mysql_driver_path() -> str:
    return MYSQL_DRIVER


# ---------------------------------------------------------------------------
# Backend port fixtures (session-scoped, Docker-internal ports)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mysql_port() -> int:
    return 3306


@pytest.fixture(scope="session")
def sqlflite_port() -> int:
    return 31337


@pytest.fixture(scope="session")
def postgres_port() -> int:
    return 5432


# ---------------------------------------------------------------------------
# FlightSQL TLS fixture (session-scoped, pre-generated cert path)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sqlflite_tls() -> tuple[int, str]:
    """Return ``(port, ca_cert_path)`` for sr-flightsql-tls service."""
    return (31337, FLIGHTSQL_CA_CERT)


# ---------------------------------------------------------------------------
# PostgreSQL SSL CA fixture (session-scoped, pre-generated cert path)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def postgres_ssl_ca() -> str:
    """Return path to pre-generated PostgreSQL CA certificate."""
    return POSTGRES_CA_CERT


# ---------------------------------------------------------------------------
# Pre-baked SQLite data fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sqlite_test_db() -> str:
    """Return path to pre-baked SQLite test database in the container."""
    return SQLITE_TEST_DB


# ---------------------------------------------------------------------------
# Structured failure capture (autouse)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def capture_on_failure(request):
    """On test failure, capture Docker Compose logs and service status."""
    yield
    rep_call = getattr(request.node, "rep_call", None)
    if rep_call is not None and rep_call.failed:
        compose_dir = os.path.join(os.path.dirname(__file__), "docker")
        try:
            all_logs = subprocess.run(
                ["docker", "compose", "logs", "--tail=100"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=compose_dir,
            )
            request.node.user_properties.append(
                ("compose_logs_all", all_logs.stdout[-8000:])
            )
        except Exception:
            pass
        try:
            sr_logs = subprocess.run(
                ["docker", "compose", "logs", "sr-main", "--tail=200"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=compose_dir,
            )
            request.node.user_properties.append(
                ("compose_logs_sr_main", sr_logs.stdout[-8000:])
            )
        except Exception:
            pass
        try:
            ps_output = subprocess.run(
                ["docker", "compose", "ps"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=compose_dir,
            )
            request.node.user_properties.append(
                ("compose_ps", ps_output.stdout)
            )
        except Exception:
            pass
