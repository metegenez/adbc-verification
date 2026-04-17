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
    *ca_cert_path* points to the extracted ``root-ca.pem``.

    Uses host port 31338 to avoid conflict with the non-TLS sqlflite on 31337.
    The container generates certs internally — we extract them via ``docker cp``
    rather than volume-mounting (which overwrites the container's tls directory
    and breaks cert generation).
    """
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
            "voltrondata/sqlflite:latest",
        ],
        check=True,
        capture_output=True,
    )

    # Wait for the TLS port to be ready (cert generation happens at startup)
    _wait_for_port("127.0.0.1", 31338, timeout=30)
    # sqlflite TLS needs extra time: cert generation + gRPC TLS server init
    time.sleep(10)

    # Extract the CA cert from the container
    tls_dir = tempfile.mkdtemp(prefix="sqlflite_tls_")
    ca_cert = pathlib.Path(tls_dir) / "root-ca.pem"

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "cp", f"{name}:/opt/sqlflite/tls/root-ca.pem", str(ca_cert)],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and ca_cert.exists() and ca_cert.stat().st_size > 0:
            return (31338, ca_cert)
        time.sleep(1)

    raise RuntimeError(f"sqlflite TLS: failed to extract root-ca.pem from {name}")
