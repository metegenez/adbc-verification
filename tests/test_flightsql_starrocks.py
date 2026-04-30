"""FlightSQL→StarRocks tests for sr-external Arrow Flight server.

Mirrors tests/test_flightsql.py structure minus the TLS scenario (D-14
plaintext only). The 22 TPC-H query coverage is delivered separately via
the canonical loader in tests/test_queries.py reading queries/tpch/q*.sql.

Covers D-15 scenarios (lifecycle, data query, wrong-password, passthrough)
against the new sr-external Compose service exposing StarRocks Arrow Flight
on grpc://sr-external:9408.
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


SR_EXTERNAL_FLIGHT_URI = "grpc://sr-external:9408"


# ---------------------------------------------------------------------------
# D-15 Scenario 1: Catalog lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_catalog_lifecycle(sr_conn, flightsql_driver_path):
    """CREATE / SHOW / SHOW DATABASES / DROP cycle on sr-external Arrow Flight."""
    cat = "test_fs_sr_lc"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={"username": "root", "password": ""},
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not found in {catalogs}"

        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        db_names = [d[0] for d in dbs]
        assert "tpch" in db_names, f"Expected 'tpch' in databases, got {db_names}"

    finally:
        drop_catalog(sr_conn, cat)

    catalogs = show_catalogs(sr_conn)
    assert cat not in catalogs, f"{cat} still present after DROP"


# ---------------------------------------------------------------------------
# D-15 Scenario 2: Data query (SHOW TABLES only — SELECT path covered by canonical TPC-H corpus)
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_data_query(sr_conn, flightsql_driver_path):
    """SHOW TABLES against sr_flightsql_starrocks.tpch — metadata fetch only.

    The full SELECT path is covered by the 22 canonical TPC-H queries in
    queries/tpch/q*.sql via the loader in tests/test_queries.py. This test
    asserts only that the catalog can enumerate tables (i.e., the metadata
    leg of Arrow Flight works).
    """
    cat = "test_fs_sr_dq"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={"username": "root", "password": ""},
        )

        rows = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.tpch")
        table_names = [r[0] for r in rows]
        for expected in ("region", "nation", "lineitem"):
            assert expected in table_names, (
                f"Expected '{expected}' in tables, got {table_names}"
            )

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-15 Scenario 3: Wrong password
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_wrong_password(sr_conn, flightsql_driver_path):
    """Wrong password fails at CREATE CATALOG (verified live: AuthenticateBasicToken).

    The defensive `pytest.raises` on first-query path is kept for symmetry in
    case a future StarRocks build delays auth probing to query time.
    """
    cat = "test_fs_sr_wp"
    drop_catalog(sr_conn, cat)
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=flightsql_driver_path,
                uri=SR_EXTERNAL_FLIGHT_URI,
                extra_props={"username": "root", "password": "wrong_password"},
            )
        except pymysql.err.DatabaseError:
            return  # Expected: fails at CREATE for StarRocks Arrow Flight

        # Defensive: if CREATE somehow succeeded, the first query MUST fail
        with pytest.raises(pymysql.err.DatabaseError):
            execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-15 Scenario 4: adbc.* passthrough
# ---------------------------------------------------------------------------

@pytest.mark.flightsql
def test_flightsql_sr_adbc_passthrough(sr_conn, flightsql_driver_path):
    """An arbitrary adbc.flight.sql.* property is forwarded without error."""
    cat = "test_fs_sr_pt"
    drop_catalog(sr_conn, cat)
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=flightsql_driver_path,
            uri=SR_EXTERNAL_FLIGHT_URI,
            extra_props={
                "username": "root",
                "password": "",
                "adbc.flight.sql.rpc.call_header.x-custom-header": "test-value",
            },
        )

        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs

    finally:
        drop_catalog(sr_conn, cat)
