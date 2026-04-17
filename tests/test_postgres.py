"""PostgreSQL backend tests for StarRocks ADBC catalog stack.

Covers D-09 scenarios (lifecycle, data round-trip, show tables, negative, pass-
through).  Uses a ``postgres:16`` Docker container as the backend.  Test data
is seeded via ``docker exec psql`` into the container.
"""

from __future__ import annotations

import subprocess

import pytest
import pymysql

from lib.catalog_helpers import (
    create_adbc_catalog,
    drop_catalog,
    execute_sql,
    show_catalogs,
)

# ---------------------------------------------------------------------------
# PostgreSQL connection constants
# ---------------------------------------------------------------------------

PG_USER = "testuser"
PG_PASS = "testpass"
PG_DB = "testdb"
PG_CONTAINER = "adbc_test_postgres"

_PG_URI = "postgresql://testuser:testpass@127.0.0.1:5432/testdb"


# ---------------------------------------------------------------------------
# Module-level fixture: seed test data via docker exec psql
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def postgres_test_data(postgres_port):
    """Seed test data into the PostgreSQL container.

    Creates a ``test_data`` table with 3 rows.  Idempotent -- uses
    ``CREATE TABLE IF NOT EXISTS`` and ``ON CONFLICT DO NOTHING``.
    """
    seed_sql = (
        "CREATE TABLE IF NOT EXISTS test_data"
        "(id INTEGER PRIMARY KEY, name VARCHAR(50), value DOUBLE PRECISION);"
        "INSERT INTO test_data VALUES(1, 'alice', 10.5) ON CONFLICT (id) DO NOTHING;"
        "INSERT INTO test_data VALUES(2, 'bob', 20.3) ON CONFLICT (id) DO NOTHING;"
        "INSERT INTO test_data VALUES(3, 'charlie', 30.1) ON CONFLICT (id) DO NOTHING;"
    )
    result = subprocess.run(
        [
            "docker", "exec", PG_CONTAINER,
            "psql", "-U", PG_USER, "-d", PG_DB, "-c", seed_sql,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to seed PostgreSQL test data: {result.stderr}"
        )
    return True  # signal that data is ready


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

        # Catalog must appear
        catalogs = show_catalogs(sr_conn)
        assert cat in catalogs, f"{cat} not found in {catalogs}"

        # SHOW DATABASES -- PostgreSQL must expose at least one database
        dbs = execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")
        assert len(dbs) >= 1, f"Expected at least 1 database, got {dbs}"

    finally:
        drop_catalog(sr_conn, cat)

    # After drop
    catalogs = show_catalogs(sr_conn)
    assert cat not in catalogs, f"{cat} still present after DROP"


# ---------------------------------------------------------------------------
# D-09 Scenario 2: Data round-trip (seeded via docker exec psql)
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_data_roundtrip(
    sr_conn, postgres_driver_path, postgres_port, postgres_test_data,
):
    """SELECT seeded rows through the StarRocks ADBC catalog.

    The PostgreSQL ADBC driver may expose the schema as ``testdb`` (DB name)
    or ``public`` (default PG schema).  We try the most likely three-part
    name patterns defensively.
    """
    cat = "test_pg_rt"
    try:
        create_adbc_catalog(
            sr_conn,
            cat,
            driver_url=postgres_driver_path,
            uri=_PG_URI,
        )

        # Try several three-part name patterns for PostgreSQL schema mapping.
        last_err: Exception | None = None
        result = None
        for fqn in (
            f"{cat}.public.test_data",
            f"{cat}.testdb.test_data",
            f"{cat}.testdb.public.test_data",
        ):
            try:
                result = execute_sql(sr_conn, f"SELECT * FROM {fqn} ORDER BY id")
                break  # success
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

        # PostgreSQL default schema is "public"
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
    """A bogus URI must produce an error at catalog creation or query time.

    Per VAL-03 the error should surface as a connection failure.
    """
    cat = "test_pg_bu"
    create_succeeded = False
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                cat,
                driver_url=postgres_driver_path,
                uri="postgresql://baduser:badpass@127.0.0.1:59999/nodb",
            )
            create_succeeded = True
        except pymysql.err.DatabaseError:
            # Error at creation time -- connection check was eager.
            return

        # CREATE succeeded -- connection is deferred; query must fail.
        with pytest.raises(pymysql.err.DatabaseError):
            execute_sql(sr_conn, f"SHOW DATABASES FROM {cat}")

    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# D-09 Scenario 4: adbc.* pass-through
# ---------------------------------------------------------------------------

@pytest.mark.postgres
def test_postgres_adbc_passthrough(sr_conn, postgres_driver_path, postgres_port):
    """Verify that an ``adbc.*`` property is forwarded to the driver.

    StarRocks must not reject ``adbc.*`` keys at validation time (PROP-05).
    The driver itself may reject unknown options — that proves forwarding works
    (the error originates from the driver, not StarRocks property validation).
    """
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
            # Driver accepted — pass-through confirmed
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            # Driver-level rejection proves StarRocks forwarded the option
            assert "Unknown database option" in err_msg or "libpq" in err_msg, (
                f"Expected driver-level rejection, got: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# TLS: Certificate-verified connection
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def postgres_ssl_ca(postgres_port) -> str:
    """Enable SSL on the PostgreSQL container and extract the CA cert.

    Returns the host-side path to the CA certificate file.
    """
    import pathlib
    import time

    ca_path = "/tmp/adbc_test_postgres_ca.pem"
    # Generate self-signed cert and enable SSL (idempotent)
    subprocess.run(
        [
            "docker", "exec", "-u", "postgres", PG_CONTAINER, "bash", "-c",
            "cd /var/lib/postgresql/data && "
            "test -f server.key || ("
            "openssl req -new -x509 -days 365 -nodes -text "
            "-out server.crt -keyout server.key "
            "-subj '/CN=localhost' 2>/dev/null && "
            "chmod 600 server.key && "
            "grep -q 'ssl = on' postgresql.conf || "
            "echo 'ssl = on' >> postgresql.conf && "
            "pg_ctl reload -D /var/lib/postgresql/data"
            ")",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    time.sleep(2)
    # Extract the server cert (self-signed = CA cert)
    subprocess.run(
        ["docker", "cp",
         f"{PG_CONTAINER}:/var/lib/postgresql/data/server.crt", ca_path],
        check=True,
        capture_output=True,
    )
    assert pathlib.Path(ca_path).exists(), f"CA cert not extracted to {ca_path}"
    return ca_path


@pytest.mark.postgres
@pytest.mark.tls
def test_postgres_tls_verified(
    sr_conn, postgres_driver_path, postgres_port, postgres_test_data,
    postgres_ssl_ca,
):
    """Connect via TLS with certificate verification using sslrootcert file path.

    Proves that the PostgreSQL ADBC driver (libpq) reads the CA cert from the
    file path in the URI and validates the server certificate against it.
    """
    tls_uri = (
        f"postgresql://{PG_USER}:{PG_PASS}@127.0.0.1:5432/{PG_DB}"
        f"?sslmode=verify-ca&sslrootcert={postgres_ssl_ca}"
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
        assert rows[0][1] == "alice"
    finally:
        drop_catalog(sr_conn, cat)
