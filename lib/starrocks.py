"""StarRocks FE/BE startup helpers, MySQL connection, and log capture."""

from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import time

import pymysql

STARROCKS_HOME = pathlib.Path(os.environ["STARROCKS_HOME"])

FE_MYSQL_PORT = 9030
FE_START_TIMEOUT_SECS = 120
BE_READY_TIMEOUT_SECS = 120


def _port_open(host: str, port: int) -> bool:
    """Return True if *host*:*port* accepts a TCP connection."""
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        return True
    except OSError:
        return False


def _mysql_connect() -> pymysql.Connection:
    """Open a pymysql connection to StarRocks FE on localhost:9030."""
    return pymysql.connect(
        host="127.0.0.1",
        port=FE_MYSQL_PORT,
        user="root",
        password="",
        database="",
        autocommit=True,
        connect_timeout=5,
    )


def _find_column_index(cursor, column_name: str) -> int:
    """Find a column index by name from ``cursor.description``.

    Raises ``RuntimeError`` if the column is not present.
    """
    for idx, desc in enumerate(cursor.description):
        if desc[0].lower() == column_name.lower():
            return idx
    raise RuntimeError(
        f"Column '{column_name}' not found in result set; "
        f"available columns: {[d[0] for d in cursor.description]}"
    )


def ensure_starrocks_running() -> pymysql.Connection:
    """Ensure FE and at least one BE are running; return a pymysql connection.

    1. Start FE if port 9030 is not open.
    2. Connect via MySQL wire protocol.
    3. Start BE if no alive backend is registered.
    4. Return the connection (FE/BE left running after tests -- per D-03).
    """
    # --- FE ---
    if not _port_open("127.0.0.1", FE_MYSQL_PORT):
        fe_start = STARROCKS_HOME / "output" / "fe" / "bin" / "start_fe.sh"
        subprocess.Popen(
            [str(fe_start), "--daemon"],
            cwd=str(STARROCKS_HOME / "output" / "fe"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + FE_START_TIMEOUT_SECS
        while time.monotonic() < deadline:
            time.sleep(2)
            if _port_open("127.0.0.1", FE_MYSQL_PORT):
                break
        else:
            raise RuntimeError(f"FE did not start within {FE_START_TIMEOUT_SECS}s")

    conn = _mysql_connect()

    # --- BE ---
    with conn.cursor() as cur:
        cur.execute("SHOW BACKENDS")
        rows = cur.fetchall()
        alive_idx = _find_column_index(cur, "Alive")
    alive = [r for r in rows if str(r[alive_idx]).lower() == "true"]

    if not alive:
        be_start = STARROCKS_HOME / "output" / "be" / "bin" / "start_be.sh"
        subprocess.Popen(
            [str(be_start), "--daemon"],
            cwd=str(STARROCKS_HOME / "output" / "be"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + BE_READY_TIMEOUT_SECS
        while time.monotonic() < deadline:
            time.sleep(3)
            with conn.cursor() as cur:
                cur.execute("SHOW BACKENDS")
                rows = cur.fetchall()
                alive_idx = _find_column_index(cur, "Alive")
            alive = [r for r in rows if str(r[alive_idx]).lower() == "true"]
            if alive:
                break
        else:
            raise RuntimeError(
                f"BE did not register within {BE_READY_TIMEOUT_SECS}s"
            )

    return conn


def tail_log(log_name: str, n: int = 50) -> str:
    """Return the last *n* lines of a StarRocks log file.

    *log_name* is ``"fe"`` or ``"be"``.
    """
    if log_name == "fe":
        path = STARROCKS_HOME / "output" / "fe" / "log" / "fe.log"
    elif log_name == "be":
        path = STARROCKS_HOME / "output" / "be" / "log" / "be.INFO"
    else:
        return f"[unknown log name: {log_name}]"
    try:
        lines = path.read_text(errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception as exc:
        return f"[could not read {path}: {exc}]"
