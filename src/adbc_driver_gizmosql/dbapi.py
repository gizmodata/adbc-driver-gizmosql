"""DBAPI 2.0 interface for GizmoSQL with OAuth/SSO support.

This module wraps ``adbc_driver_flightsql.dbapi`` and adds GizmoSQL-specific
connection logic, including OAuth browser flow for ``auth_type="external"``.

All standard DBAPI 2.0 symbols are re-exported from
``adbc_driver_flightsql.dbapi`` so this module can be used as a drop-in
replacement.

Example (password auth)::

    from adbc_driver_gizmosql import dbapi as gizmosql

    with gizmosql.connect("grpc+tls://localhost:31337",
                          username="user", password="pass",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print(cur.fetch_arrow_table())

Example (DDL/DML — executes immediately without fetching)::

    from adbc_driver_gizmosql import dbapi as gizmosql

    with gizmosql.connect("grpc+tls://localhost:31337",
                          username="user", password="pass",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            gizmosql.execute_update(cur, "CREATE TABLE t (a INT)")
            rows_affected = gizmosql.execute_update(cur, "INSERT INTO t VALUES (1)")
            print(f"Rows affected: {rows_affected}")

Example (OAuth/SSO)::

    from adbc_driver_gizmosql import dbapi as gizmosql

    with gizmosql.connect("grpc+tls://localhost:31337",
                          auth_type="external",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER")
            print(cur.fetch_arrow_table())
"""

from __future__ import annotations

from typing import Optional

from adbc_driver_flightsql import DatabaseOptions
from adbc_driver_flightsql import dbapi as _flightsql_dbapi

# Re-export all DBAPI 2.0 symbols from the underlying driver
from adbc_driver_flightsql.dbapi import (  # noqa: F401
    Connection,
    Cursor,
    Date,
    DateFromTicks,
    Time,
    TimeFromTicks,
    Timestamp,
    TimestampFromTicks,
    apilevel,
    paramstyle,
    threadsafety,
)

from ._oauth import DEFAULT_OAUTH_PORT, get_oauth_token


def connect(
    uri: str,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    tls_skip_verify: bool = False,
    auth_type: str = "password",
    oauth_port: int = DEFAULT_OAUTH_PORT,
    oauth_url: Optional[str] = None,
    oauth_tls_skip_verify: Optional[bool] = None,
    oauth_timeout: int = 300,
    open_browser: bool = True,
    db_kwargs: Optional[dict[str, str]] = None,
    conn_kwargs: Optional[dict[str, str]] = None,
    autocommit: bool = True,
) -> Connection:
    """Connect to a GizmoSQL server via ADBC Flight SQL.

    Args:
        uri: Flight SQL URI (e.g., ``"grpc+tls://localhost:31337"``).
        username: Username for password authentication.
        password: Password for password authentication.
        tls_skip_verify: Skip TLS certificate verification for the
            Flight SQL connection.
        auth_type: Authentication type: ``"password"`` (default) or
            ``"external"`` (OAuth/SSO browser flow).
        oauth_port: OAuth HTTP server port (default: 31339).
        oauth_url: Explicit OAuth base URL. If not provided, auto-discovers.
        oauth_tls_skip_verify: Skip TLS verification for the OAuth server.
            Defaults to the value of ``tls_skip_verify``.
        oauth_timeout: Seconds to wait for OAuth completion (default: 300).
        open_browser: Automatically open the browser for OAuth (default: True).
        db_kwargs: Additional database keyword arguments passed to
            ``adbc_driver_flightsql``.
        conn_kwargs: Additional connection keyword arguments passed to
            ``adbc_driver_flightsql``.
        autocommit: Enable autocommit (default: True).

    Returns:
        A DBAPI 2.0 Connection object.

    Raises:
        GizmoSQLOAuthError: If the OAuth flow fails.
        ValueError: If required parameters are missing for the chosen auth type.
    """
    if db_kwargs is None:
        db_kwargs = {}
    else:
        db_kwargs = dict(db_kwargs)

    if conn_kwargs is None:
        conn_kwargs = {}
    else:
        conn_kwargs = dict(conn_kwargs)

    if tls_skip_verify:
        db_kwargs.setdefault(DatabaseOptions.TLS_SKIP_VERIFY.value, "true")

    if oauth_tls_skip_verify is None:
        oauth_tls_skip_verify = tls_skip_verify

    if auth_type == "external":
        # Extract host from URI for OAuth discovery
        host = _extract_host(uri)
        result = get_oauth_token(
            host=host,
            port=oauth_port,
            tls_skip_verify=oauth_tls_skip_verify,
            timeout=oauth_timeout,
            open_browser=open_browser,
            oauth_url=oauth_url,
        )
        db_kwargs["username"] = "token"
        db_kwargs["password"] = result.token

    elif auth_type == "password":
        if username is not None:
            db_kwargs.setdefault("username", username)
        if password is not None:
            db_kwargs.setdefault("password", password)
    else:
        raise ValueError(
            f"Invalid auth_type: {auth_type!r}. Must be 'password' or 'external'."
        )

    return _flightsql_dbapi.connect(
        uri,
        db_kwargs=db_kwargs,
        conn_kwargs=conn_kwargs,
        autocommit=autocommit,
    )


def execute_update(cursor: Cursor, query: str) -> int:
    """Execute a DDL/DML statement immediately and return the rows affected.

    This is a convenience wrapper that calls the ADBC statement's
    ``execute_update()`` method directly (the server's
    ``DoPutPreparedStatementUpdate`` RPC).  Unlike ``cursor.execute()``,
    this fires the statement immediately on the server **without requiring
    a fetch**, making it the preferred way to run DDL (``CREATE``, ``DROP``,
    ``ALTER``) and DML (``INSERT``, ``UPDATE``, ``DELETE``) statements with
    GizmoSQL's lazy-execution model.

    Args:
        cursor: An open DBAPI 2.0 cursor obtained from ``connection.cursor()``.
        query: The SQL DDL or DML statement to execute.

    Returns:
        The number of rows affected (``-1`` when the server does not report
        a count, e.g. for DDL statements).

    Example::

        with conn.cursor() as cur:
            gizmosql.execute_update(cur, "CREATE TABLE t (a INT)")
            rows = gizmosql.execute_update(cur, "INSERT INTO t VALUES (1)")
            print(f"Rows affected: {rows}")
    """
    cursor.adbc_statement.set_sql_query(query)
    return cursor.adbc_statement.execute_update()


def _extract_host(uri: str) -> str:
    """Extract the hostname from a Flight SQL URI.

    Handles URIs like:
        grpc://host:port
        grpc+tls://host:port
        grpc+tcp://host:port
    """
    # Remove scheme
    if "://" in uri:
        remainder = uri.split("://", 1)[1]
    else:
        remainder = uri

    # Remove port
    if ":" in remainder:
        host = remainder.rsplit(":", 1)[0]
    else:
        host = remainder

    # Remove trailing slash
    return host.rstrip("/")
