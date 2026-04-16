"""Negative tests -- consolidated error-path validation across VAL-01..05, PROP-02..05.

# Run: STARROCKS_HOME=/path/to/starrocks .venv/bin/pytest tests/ --json-report --json-report-file=reports/latest.json -v
# JSON report will be at reports/latest.json with per-test pass/fail and user_properties for failure diagnostics (D-12/D-13)

Covers all externally-triggerable failure classes:
  - PROP-02: mutual exclusion of driver_url / driver_name
  - VAL-03: file not found, bad entrypoint symbol
  - VAL-04: unknown top-level property key (error names the key)
  - PROP-05: adbc.* pass-through acceptance (positive control)
  - Duplicate catalog name rejection

These tests do not depend on any specific backend Docker container -- they use
the SQLite driver path (local, always available) as the valid baseline.
"""

from __future__ import annotations

import pymysql
import pytest

from lib.catalog_helpers import create_adbc_catalog, drop_catalog, execute_sql


# ---------------------------------------------------------------------------
# Test 1: Both driver_url and driver_name present (PROP-02 mutual exclusion)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_both_driver_url_and_name_rejected(sr_conn, sqlite_driver_path):
    """Setting both driver_url and driver_name must be rejected at DDL time.

    PROP-02: Exactly one of driver_url or driver_name is required.
    Both present is a validation error.
    """
    cat = "test_neg_both"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            # Build SQL manually because driver_name is a top-level key (PROP-04)
            # that create_adbc_catalog doesn't expose directly.
            sql = f'''CREATE EXTERNAL CATALOG {cat} PROPERTIES(
                "type"="adbc",
                "driver_url"="{sqlite_driver_path}",
                "driver_name"="some_driver",
                "uri"=":memory:"
            )'''
            with sr_conn.cursor() as cur:
                cur.execute(sql)

        # Error should indicate mutual exclusion
        err_msg = str(exc_info.value).lower()
        assert (
            "driver_url" in err_msg or "driver_name" in err_msg
            or "both" in err_msg or "mutual" in err_msg
            or "exclusive" in err_msg or "one of" in err_msg
        ), (
            f"Error should reference driver_url/driver_name mutual exclusion, "
            f"got: {exc_info.value}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 2: Neither driver_url nor driver_name present (PROP-02 missing both)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_neither_driver_url_nor_name_rejected(sr_conn):
    """Omitting both driver_url and driver_name must be rejected at DDL time.

    PROP-02: Exactly one of driver_url or driver_name is required.
    Neither present is a validation error.
    """
    cat = "test_neg_neither"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            sql = f'''CREATE EXTERNAL CATALOG {cat} PROPERTIES(
                "type"="adbc",
                "uri"=":memory:"
            )'''
            with sr_conn.cursor() as cur:
                cur.execute(sql)

        # Error should indicate neither is set
        err_msg = str(exc_info.value).lower()
        assert (
            "driver_url" in err_msg or "driver_name" in err_msg
            or "neither" in err_msg or "required" in err_msg
            or "must" in err_msg or "missing" in err_msg
        ), (
            f"Error should reference missing driver_url/driver_name, "
            f"got: {exc_info.value}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 3: Unknown top-level key names the key (VAL-04)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_unknown_top_level_key_names_the_key(sr_conn, sqlite_driver_path):
    """An unknown non-adbc.* top-level property must be rejected, naming the key.

    VAL-04: Error message must contain the unknown key name so the user knows
    exactly which property to fix.
    """
    cat = "test_neg_unk"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                uri=":memory:",
                extra_props={"weird_unknown_key": "val"},
            )

        # VAL-04: error message must name the unknown key
        err_msg = str(exc_info.value)
        assert "weird_unknown_key" in err_msg, (
            f"Error message should contain 'weird_unknown_key', got: {err_msg}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 4: Nonexistent driver_url path (VAL-03 file not found)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_nonexistent_driver_url_path(sr_conn):
    """A driver_url pointing to a nonexistent file must raise an error.

    VAL-03: Error should reference the path or indicate file not found.
    """
    cat = "test_neg_nofile"
    bad_path = "/does/not/exist/libfake_driver.so"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=bad_path,
                uri=":memory:",
            )

        # Error should reference the bad path
        err_msg = str(exc_info.value)
        assert (
            "/does/not/exist/" in err_msg
            or "libfake_driver" in err_msg
            or "not found" in err_msg.lower()
            or "no such file" in err_msg.lower()
            or "cannot open" in err_msg.lower()
        ), (
            f"Error should reference the bad driver path, got: {err_msg}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 5: Bad entrypoint symbol (VAL-03 entrypoint missing)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_bad_entrypoint_symbol(sr_conn, sqlite_driver_path):
    """A nonexistent entrypoint symbol must raise an error at catalog creation.

    VAL-03: Error should reference the entrypoint symbol or indicate it was
    not found in the driver shared library.
    """
    cat = "test_neg_badep"
    try:
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                entrypoint="NonExistentInitFunction",
                uri=":memory:",
            )

        # Error should reference the entrypoint symbol
        err_msg = str(exc_info.value)
        assert (
            "NonExistentInitFunction" in err_msg
            or "entrypoint" in err_msg.lower()
            or "symbol" in err_msg.lower()
            or "init" in err_msg.lower()
        ), (
            f"Error should reference the bad entrypoint symbol, got: {err_msg}"
        )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 6: adbc.* prefixed key is NOT rejected (PROP-05 positive control)
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_adbc_prefixed_key_not_rejected(sr_conn, sqlite_driver_path):
    """adbc.* keys are pass-through — StarRocks must NOT reject them at validation.

    PROP-05: Any property starting with ``adbc.`` is forwarded verbatim to
    the driver. The driver itself may reject unknown options, but that error
    comes from the driver, not StarRocks property validation.
    """
    cat = "test_neg_adbc_pt"
    try:
        try:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                uri=":memory:",
                extra_props={"adbc.some.arbitrary.option": "arbitrary_value"},
            )
            # Driver accepted it — pass-through confirmed
        except pymysql.err.ProgrammingError as e:
            err_msg = str(e)
            # If the error comes from the DRIVER (not StarRocks validation),
            # that proves the adbc.* key was forwarded — PROP-05 is satisfied.
            # StarRocks validation errors say "Unknown catalog property" or similar.
            # Driver errors say "Unknown database option" or driver-specific text.
            assert (
                "Unknown database option" in err_msg
                or "SQLite" in err_msg
                or "connection to driver" in err_msg
            ), (
                f"Expected driver-level rejection (proving pass-through), "
                f"but got what looks like a StarRocks validation error: {err_msg}"
            )
    finally:
        drop_catalog(sr_conn, cat)


# ---------------------------------------------------------------------------
# Test 7: Duplicate catalog name rejected
# ---------------------------------------------------------------------------

@pytest.mark.negative
def test_duplicate_catalog_name_rejected(sr_conn, sqlite_driver_path):
    """Creating two catalogs with the same name must fail on the second attempt.

    StarRocks rejects duplicate catalog names at DDL time.
    """
    cat = "test_neg_dup"
    try:
        # First creation should succeed
        create_adbc_catalog(
            sr_conn,
            catalog_name=cat,
            driver_url=sqlite_driver_path,
            uri=":memory:",
        )

        # Second creation with the same name should fail
        with pytest.raises(
            (pymysql.err.OperationalError, pymysql.err.InternalError,
             pymysql.err.DatabaseError)
        ) as exc_info:
            create_adbc_catalog(
                sr_conn,
                catalog_name=cat,
                driver_url=sqlite_driver_path,
                uri=":memory:",
            )

        # Error should indicate the catalog already exists
        err_msg = str(exc_info.value).lower()
        assert (
            "exist" in err_msg or "duplicate" in err_msg
            or "already" in err_msg or cat in err_msg.lower()
        ), (
            f"Error should indicate catalog already exists, got: {exc_info.value}"
        )
    finally:
        drop_catalog(sr_conn, cat)
