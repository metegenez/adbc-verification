"""SQL helpers for StarRocks ADBC catalog lifecycle."""

from __future__ import annotations


def create_adbc_catalog(
    conn,
    catalog_name: str,
    driver_url: str,
    uri: str = "",
    extra_props: dict | None = None,
    entrypoint: str = "",
) -> None:
    """Issue ``CREATE EXTERNAL CATALOG`` via the given pymysql connection.

    *driver_url* is the filesystem path to the ADBC driver ``.so``.
    Optional *uri* sets the ``uri`` property (e.g. a connection string).
    Optional *entrypoint* sets ``driver_entrypoint`` (required for DuckDB).
    *extra_props* are merged into the ``PROPERTIES(...)`` clause.
    """
    props: dict[str, str] = {
        "type": "adbc",
        "driver_url": driver_url,
    }
    if uri:
        props["uri"] = uri
    if entrypoint:
        props["driver_entrypoint"] = entrypoint
    if extra_props:
        props.update(extra_props)

    # Escape double quotes in values. Newlines are kept raw — StarRocks SQL
    # accepts them inside quoted property values (needed for PEM certificates).
    def _escape(v: str) -> str:
        return v.replace('"', '\\"')

    props_sql = ", ".join(f'"{k}"="{_escape(v)}"' for k, v in props.items())
    sql = f"CREATE EXTERNAL CATALOG {catalog_name} PROPERTIES({props_sql})"
    with conn.cursor() as cur:
        cur.execute(sql)



def create_jdbc_catalog(
    conn,
    catalog_name: str,
    jdbc_uri: str,
    user: str,
    password: str,
    driver_url: str,
    driver_class: str = "com.mysql.cj.jdbc.Driver",
) -> None:
    """Issue ``CREATE EXTERNAL CATALOG`` for a JDBC source via pymysql.

    Property key is ``user`` (NOT ``username`` — that key is ADBC-specific,
    see ``create_adbc_catalog`` and CLAUDE.md). Properties emitted:
    type=jdbc, user, password, jdbc_uri, driver_url, driver_class.

    *driver_url* must be the absolute path to the JAR inside the StarRocks
    container (e.g. ``/opt/starrocks/drivers/mysql-connector-j-9.3.0.jar``).
    Glob patterns are NOT expanded by StarRocks — pin the exact filename.
    """
    props: dict[str, str] = {
        "type": "jdbc",
        "user": user,
        "password": password,
        "jdbc_uri": jdbc_uri,
        "driver_url": driver_url,
        "driver_class": driver_class,
    }

    def _escape(v: str) -> str:
        return v.replace('"', '\\"')

    props_sql = ", ".join(f'"{k}"="{_escape(v)}"' for k, v in props.items())
    sql = f"CREATE EXTERNAL CATALOG {catalog_name} PROPERTIES({props_sql})"
    with conn.cursor() as cur:
        cur.execute(sql)


def drop_catalog(conn, catalog_name: str) -> None:
    """Issue ``DROP CATALOG IF EXISTS``."""
    with conn.cursor() as cur:
        cur.execute(f"DROP CATALOG IF EXISTS {catalog_name}")


def show_catalogs(conn) -> list[str]:
    """Return the list of catalog names from ``SHOW CATALOGS``."""
    with conn.cursor() as cur:
        cur.execute("SHOW CATALOGS")
        return [row[0] for row in cur.fetchall()]


def execute_sql(conn, sql: str) -> list[tuple]:
    """Execute arbitrary SQL and return ``fetchall()`` results."""
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()
