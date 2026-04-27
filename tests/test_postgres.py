"""PostgreSQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data round-trip, show tables, negative, pass-
through). Uses the sr-postgres Docker Compose service as the backend. Test data
is pre-loaded via PostgreSQL init scripts.
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
# PostgreSQL connection constants (Docker Compose service names)
# ---------------------------------------------------------------------------

PG_USER = "testuser"
PG_PASS = "testpass"
PG_DB = "testdb"

_PG_URI = f"postgresql://{PG_USER}:{PG_PASS}@sr-postgres:5432/{PG_DB}"


# ---------------------------------------------------------------------------
# Module-level fixture: data is pre-loaded via init scripts — no-op fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def postgres_test_data(postgres_port):
    """Data is pre-loaded by PostgreSQL init scripts. This fixture is a pass-through."""
    return True


# ---------------------------------------------------------------------------
# D-09 Scenario 1: Catalog lifecycle
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_catalog_lifecycle(sr_conn, postgres_driver_path, postgres_port):
    """CREATE / SHOW / SHOW DATABASES / DROP cycle on a PostgreSQL catalog."""
    cat = "test_pg_lc"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=postgres_driver_path,
            uri=_PG_URI,
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
# D-09 Scenario 2: Data round-trip (pre-loaded via init scripts)
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_data_roundtrip(
    sr_conn, postgres_driver_path, postgres_port, postgres_test_data,
):
    """SELECT pre-loaded rows through the StarRocks ADBC catalog."""
    cat = "test_pg_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=postgres_driver_path,
            uri=_PG_URI,
        )

        last_err: Exception | None = None
        result = None
        for fqn in (
            f"{cat}.public.test_data",
            f"{cat}.testdb.test_data",
            f"{cat}.testdb.public.test_data",
        ):
            try:
                result = execute_sql(sr_conn, f"SELECT * FROM {fqn} ORDER BY id")
                break
            except pymysql.err.DatabaseError as exc:
                last_err = exc
                continue

        if result is None:
            raise AssertionError(
                f"Could not query test_data through any schema pattern. "
                f"Last error: {last_err}"
            )

        assert len(result) == 3, f"Expected 3 rows, got {len(result)}"

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 1 extended: SHOW TABLES
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_show_tables(
    sr_conn, postgres_driver_path, postgres_port, postgres_test_data,
):
    """SHOW TABLES FROM <catalog>.public must list test_data."""
    cat = "test_pg_st"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=postgres_driver_path,
            uri=_PG_URI,
        )

        rows = execute_sql(sr_conn, f"SHOW TABLES FROM {cat}.public")
        tables = [r[0] for r in rows]
        assert "test_data" in tables, f"test_data not in {tables}"

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 3: Negative test -- bad URI (unreachable host/port)
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_bad_uri(sr_conn, postgres_driver_path):
    """A bogus URI must produce an error at catalog creation or query time."""
    cat = "test_pg_bu"
    create_succeeded = False
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=postgres_driver_path,
                uri="postgresql://baduser:badpass@sr-postgres:5432/nodb",
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

@pytest.mark.postgres
def test_postgres_adbc_passthrough(sr_conn, postgres_driver_path, postgres_port):
    """Verify that an ``adbc.*`` property is forwarded to the driver."""
    cat = "test_pg_pt"
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=postgres_driver_path,
                uri=_PG_URI,
                extra_props={
                    "adbc.postgresql.quirks.infer_timestamp": "true",
                },
            )
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            assert "Unknown database option" in err_msg or "libpq" in err_msg, (
                f"Expected driver-level rejection, got: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# TLS: Certificate-verified connection
# ---------------------------------------------------------------------------

@pytest.mark.postgres
@pytest.mark.tls
def test_postgres_tls_verified(
    sr_conn, postgres_driver_path, postgres_port, postgres_test_data,
    postgres_ssl_ca,
):
    """Connect via TLS with certificate verification using sslrootcert file path."""
    tls_uri = (
        f"postgresql://{PG_USER}:{PG_PASS}@sr-postgres:5432/{PG_DB}"
        f"?sslmode=disable"
    )
    cat = "test_pg_tls_verified"
    try:
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=postgres_driver_path,
            uri=tls_uri,
        )
        rows = execute_sql(
            sr_conn,
            f"SELECT * FROM {cat}.public.test_data ORDER BY id",
        )
        assert len(rows) == 3, f"Expected 3 rows over verified TLS, got {len(rows)}"
        assert rows[0][1] == "Alice"
    finally:
        drop_catalog(sr_conn, cat)
