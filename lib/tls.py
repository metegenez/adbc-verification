"""TLS helpers for sqlflite with self-signed certificates."""

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import time

from lib.docker_backends import _wait_for_port


def start_sqlflite_tls(
    name: str = "adbc_test_sqlflite_tls",
) -> tuple[int, pathlib.Path]:
    """Start sqlflite with TLS enabled.

    Returns ``(port, ca_cert_path)`` where *port* is 31338 (host-side) and
    *ca_cert_path* points to ``root-ca.pem`` in a temporary directory that
    sqlflite populates via a volume mount.

    Uses host port 31338 to avoid conflict with the non-TLS sqlflite on 31337.
    """
    tls_dir = tempfile.mkdtemp(prefix="sqlflite_tls_")

    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    subprocess.run(
        [
            "docker", "run",
            "--name", name,
            "--detach", "--rm", "--tty", "--init",
            "--publish", "31338:31337",
            "--env", "TLS_ENABLED=1",
            "--env", "SQLFLITE_PASSWORD=sqlflite_password",
            "--env", "PRINT_QUERIES=1",
            "--volume", f"{tls_dir}:/opt/sqlflite/tls",
            "voltrondata/sqlflite:latest",
        ],
        check=True,
        capture_output=True,
    )

    # Pitfall 3: cert may not be written yet even when port opens.
    # Poll for root-ca.pem existence AND non-zero size.
    ca_cert = pathlib.Path(tls_dir) / "root-ca.pem"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if ca_cert.exists() and ca_cert.stat().st_size > 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError(
            f"sqlflite TLS: root-ca.pem not generated within 30s at {ca_cert}"
        )

    # Now wait for the TLS port to be ready.
    _wait_for_port("127.0.0.1", 31338, timeout=10)

    return (31338, ca_cert)
