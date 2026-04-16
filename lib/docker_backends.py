"""Docker container lifecycle helpers for ADBC test backends."""

from __future__ import annotations

import socket
import subprocess
import time


def _wait_for_port(host: str, port: int, timeout: int = 30) -> None:
    """Block until *host*:*port* accepts a TCP connection.

    Raises ``RuntimeError`` on timeout.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.create_connection((host, port), timeout=2)
            s.close()
            return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"Port {host}:{port} not open after {timeout}s")


# ---------------------------------------------------------------------------
# sqlflite (FlightSQL) -- voltrondata/sqlflite:latest
# ---------------------------------------------------------------------------

def start_sqlflite_no_tls(name: str = "adbc_test_sqlflite") -> int:
    """Start sqlflite without TLS.  Returns port (31337)."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker", "run",
            "--name", name,
            "--detach", "--rm", "--tty", "--init",
            "--publish", "31337:31337",
            "--env", "TLS_ENABLED=0",
            "--env", "SQLFLITE_PASSWORD=sqlflite_password",
            "--env", "PRINT_QUERIES=1",
            "--pull", "missing",
            "voltrondata/sqlflite:latest",
        ],
        check=True,
        capture_output=True,
    )
    _wait_for_port("127.0.0.1", 31337, timeout=30)
    return 31337


def ensure_sqlflite_running(name: str = "adbc_test_sqlflite") -> int:
    """Return 31337 if sqlflite is already running, otherwise start it."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip() == "true":
        return 31337
    return start_sqlflite_no_tls(name)


# ---------------------------------------------------------------------------
# PostgreSQL -- postgres:16
# ---------------------------------------------------------------------------

def start_postgres(name: str = "adbc_test_postgres") -> int:
    """Start PostgreSQL 16.  Returns port (5432)."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker", "run",
            "--name", name,
            "--detach", "--rm",
            "--publish", "5432:5432",
            "--env", "POSTGRES_PASSWORD=testpass",
            "--env", "POSTGRES_USER=testuser",
            "--env", "POSTGRES_DB=testdb",
            "postgres:16",
        ],
        check=True,
        capture_output=True,
    )
    _wait_for_port("127.0.0.1", 5432, timeout=30)
    # Pitfall 6: Postgres needs extra time to init data directory after port opens.
    time.sleep(3)
    return 5432


def ensure_postgres_running(name: str = "adbc_test_postgres") -> int:
    """Return 5432 if PostgreSQL is already running, otherwise start it."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip() == "true":
        return 5432
    return start_postgres(name)


# ---------------------------------------------------------------------------
# Generic container stop
# ---------------------------------------------------------------------------

def stop_container(name: str) -> None:
    """Stop a Docker container by name (ignores errors)."""
    subprocess.run(["docker", "stop", name], capture_output=True)
