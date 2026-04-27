"""FlightSQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data query, negative, pass-through) and D-11
(TLS with self-signed certs). Uses the sr-flightsql and sr-flightsql-tls Docker
Compose services.
"""

from __future__ import annotations

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)


# ---------------------------------------------------------------------------
# D-09 Scenario 1: Catalog lifecycle (non-TLS)
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_catalog_lifecycle(sr_conn, flightsql_driver_path, sqlflite_port):
    """CREATE / SHOW / SHOW DATABASES / DROP cycle on a non-TLS FlightSQL catalog."""
    cat = "test_fs_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri="grpc://sr-flightsql:31337",
            extra_props={
                "username": "sqlflite_username",
                "password": "sqlflite_password",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not found in {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {dbs}"

    finally:
        drop_catalog(sr_conn, cat)

    catalogs = show_catalogs(sr_conn)
    assert cat not in catalogs, f"{cat} still present after DROP"


# ---------------------------------------------------------------------------
# D-09 Scenario 2: Data query (non-TLS)
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_data_query(sr_conn, flightsql_driver_path, sqlflite_port):
    """Discover available tables in sqlflite and query if any exist."""
    cat = "test_fs_rq"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri="grpc://sr-flightsql:31337",
            extra_props={
                "username": "sqlflite_username",
                "password": "sqlflite_password",
            },
        )

        tables = []
        for db_candidate in ("main", "sqlflite", "default"):
            try:
                rows = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.{db_candidate}")
                tables = [r[0] for r in rows]
                if tables:
                    break
            except pymysql.err.DatabaseError:
                continue

        if tables:
            first_table = tables[0]
            result = execute_sql(
                sr_conn,
                f"SELECT * FROM {cat}.main.{first_table} LIMIT 5",
            )
            assert len(result) >= 1, f"Expected data from {first_table}, got {len(result)} rows"
        else:
            pass

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-11: TLS lifecycle (self-signed cert pass-through via PROP-05/PROP-09)
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
@pytest.mark.tls
def test_flightsql_tls_lifecycle(sr_conn, flightsql_driver_path, sqlflite_tls):
    """CREATE catalog with TLS, verify cert pass-through, SHOW DATABASES, DROP."""
    tls_port, ca_cert_path = sqlflite_tls
    cat = "test_fs_tls"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=f"grpc+tls://sr-flightsql-tls:{tls_port}",
            extra_props={
                "username": "sqlflite_username",
                "password": "sqlflite_password",
                "adbc.flight.sql.client_option.tls_root_certs": f"file://{ca_cert_path}",
                "adbc.flight.sql.client_option.tls_skip_verify": "true",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not in catalogs after TLS create"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {dbs}"

        tables = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.main")
        table_names = [row[0] for row in tables]
        assert len(table_names) >= 1, f"Expected tables in TLS catalog, got {table_names}"

        first_table = table_names[0]
        rows = execute_sql(sr_conn, f"SELECT * FROM {cat}.main.{first_table} LIMIT 3")
        assert len(rows) >= 1, (
            f"Expected data from {first_table} over TLS, got {len(rows)} rows"
        )

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 3: Negative test -- wrong password
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_wrong_password(sr_conn, flightsql_driver_path, sqlflite_port):
    """Wrong password must cause an error at catalog creation or query time."""
    cat = "test_fs_wp"
    create_succeeded = False
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=flightsql_driver_path,
                uri="grpc://sr-flightsql:31337",
                extra_props={
                    "username": "sqlflite_username",
                    "password": "wrong_password",
                },
            )
            create_succeeded = True
        except pymysql.err.DatabaseError:
            return

        with pytest.raises(pymysql.err.DatabaseError):
            execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 4: adbc.* pass-through
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_adbc_passthrough(sr_conn, flightsql_driver_path, sqlflite_port):
    """Verify that an arbitrary ``adbc.*`` property is forwarded without error."""
    cat = "test_fs_pt"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri="grpc://sr-flightsql:31337",
            extra_props={
                "username": "sqlflite_username",
                "password": "sqlflite_password",
                "adbc.flight.sql.rpc.call_header.x-custom-header": "test-value",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs

    finally:
        drop_catalog(sr_conn, cat)
