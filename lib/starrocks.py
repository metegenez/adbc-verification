"""StarRocks MySQL connection helper (Docker Compose mode).

In Docker Compose mode, StarRocks FE/BE are started and managed by the
container entrypoint and Docker Compose healthchecks. This module is a
thin wrapper around ``pymysql.connect`` for convenience.
"""

from __future__ import annotations

import pymysql


def connect(host: str = "127.0.0.1", port: int = 9030) -> pymysql.Connection:
    """Open a pymysql connection to StarRocks FE."""
    return _mysql_connect(host, port)


def _mysql_connect(host: str = "127.0.0.1", port: int = 9030) -> pymysql.Connection:
    """Open a pymysql connection to StarRocks FE on *host*:*port*."""
    return pymysql.connect(
        host=host,
        port=port,
        user="root",
        password="",
        autocommit=True,
    )
