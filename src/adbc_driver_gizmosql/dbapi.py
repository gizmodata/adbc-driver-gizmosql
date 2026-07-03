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

Example (DDL/DML — auto-detected and executed immediately)::

    from adbc_driver_gizmosql import dbapi as gizmosql

    with gizmosql.connect("grpc+tls://localhost:31337",
                          username="user", password="pass",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE t (a INT)")
            cur.execute("INSERT INTO t VALUES (1)")
            cur.execute("SELECT * FROM t")
            print(cur.fetch_arrow_table())

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

import re as _re
import threading
from typing import Any, Dict, Optional, Union

import adbc_driver_flightsql
import adbc_driver_manager
from adbc_driver_flightsql import DatabaseOptions
from adbc_driver_flightsql.dbapi import (
    Connection as _BaseConnection,
)
from adbc_driver_flightsql.dbapi import (
    Cursor as _BaseCursor,
)

# Re-export all DBAPI 2.0 symbols from the underlying driver
from adbc_driver_flightsql.dbapi import (  # noqa: F401
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

# SQL keywords that indicate DDL/DML statements (not SELECT/WITH/SHOW/etc.).
# When execute() sees one of these as the first keyword, it routes through
# execute_update() (DoPut RPC) for immediate server-side execution.
_DDL_DML_KEYWORDS = frozenset({
    "ALTER",
    "ATTACH",
    "BEGIN",
    "CALL",
    "CHECKPOINT",
    "COMMENT",
    "COMMIT",
    "COPY",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "EXPORT",
    "GRANT",
    "IMPORT",
    "INSERT",
    "INSTALL",
    "LOAD",
    "MERGE",
    "REVOKE",
    "ROLLBACK",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "USE",
    "VACUUM",
})


_BLOCK_COMMENT_RE = _re.compile(pattern=r"/\*.*?\*/", flags=_re.DOTALL)
_LINE_COMMENT_RE = _re.compile(pattern=r"--[^\n]*")
# Strip single- and double-quoted string literals. SQL doubles the quote
# character to escape it (''), so the regex consumes any number of either
# (chars-other-than-quote) or (doubled-quote) before the closing quote.
_SINGLE_QUOTED_RE = _re.compile(pattern=r"'(?:[^']|'')*'")
_DOUBLE_QUOTED_RE = _re.compile(pattern=r'"(?:[^"]|"")*"')
# Word-boundary RETURNING — DML statements with a RETURNING clause produce a
# result set and must NOT be routed through the DoPut/execute_update path.
_RETURNING_RE = _re.compile(pattern=r"\bRETURNING\b", flags=_re.IGNORECASE)


def _strip_sql_comments(sql: str) -> str:
    """Strip SQL block (/* ... */) and line (-- ...) comments."""
    sql = _BLOCK_COMMENT_RE.sub("", sql)
    sql = _LINE_COMMENT_RE.sub("", sql)
    return sql.lstrip()


def _has_returning_clause(sql: str) -> bool:
    """Return True if the SQL contains a ``RETURNING`` keyword outside of
    string literals. Comments must already be stripped by the caller.

    DuckDB's ``INSERT ... RETURNING`` / ``UPDATE ... RETURNING`` /
    ``DELETE ... RETURNING`` produce a result set, so the cursor must take
    the lazy GetFlightInfo→DoGet path rather than DoPut/execute_update
    (which only returns a row count and discards the rows).
    """
    # Remove string literals so the word "RETURNING" inside a string value
    # (e.g. INSERT INTO t VALUES ('returning')) does not trigger a match.
    without_strings = _SINGLE_QUOTED_RE.sub(repl="''", string=sql)
    without_strings = _DOUBLE_QUOTED_RE.sub(repl='""', string=without_strings)
    return _RETURNING_RE.search(string=without_strings) is not None


class _CachedRowIterator:
    """Stand-in for ``adbc_driver_manager.dbapi._RowIterator`` that serves an
    already-materialized ``pyarrow.Table``.

    Used after eager-materializing ``INSERT/UPDATE/DELETE ... RETURNING`` so
    the underlying DML actually fires regardless of whether the caller chooses
    to fetch — see ``Cursor.execute()`` for the rationale.

    Implements just the surface area that ``Cursor`` reaches into on
    ``self._results`` (description, rownumber, fetchone/fetchmany/fetchall,
    fetch_arrow_table/fetch_df/fetch_polars, close).
    """

    def __init__(self, table) -> None:
        self._table = table
        self._row_idx = 0
        self.rownumber = 0

    @property
    def description(self):
        if self._table is None:
            return []
        return [
            (field.name, field.type, None, None, None, None, None)
            for field in self._table.schema
        ]

    def fetchone(self):
        if self._table is None or self._row_idx >= self._table.num_rows:
            return None
        row = tuple(c[self._row_idx].as_py() for c in self._table.columns)
        self._row_idx += 1
        self.rownumber += 1
        return row

    def fetchmany(self, size: int):
        rows = []
        for _ in range(size):
            r = self.fetchone()
            if r is None:
                break
            rows.append(r)
        return rows

    def fetchall(self):
        rows = []
        while True:
            r = self.fetchone()
            if r is None:
                break
            rows.append(r)
        return rows

    def fetch_arrow_table(self):
        return self._table

    def fetch_df(self):
        return self._table.to_pandas()

    def fetch_polars(self):
        import polars

        return polars.from_arrow(self._table)

    def close(self) -> None:
        self._table = None


def _is_ddl_dml(operation) -> bool:
    """Return True if the SQL statement is DDL/DML based on the first keyword.

    Strips SQL comments first so that query-comment prefixes (e.g., dbt's
    ``/* {"app": "dbt", ...} */``) don't mask the actual statement keyword.

    INSERT/UPDATE/DELETE statements with a ``RETURNING`` clause are *not*
    classified as pure DDL/DML here: they produce a result set and must
    take the regular query path so the caller can ``fetch_arrow_table()``
    the returned rows. Without this carve-out the ``RETURNING`` rows would
    be silently discarded by the DoPut/execute_update code path.
    """
    if not isinstance(operation, str):
        return False
    stripped = _strip_sql_comments(operation)
    if not stripped:
        return False
    # Extract the first word (token before whitespace or opening paren)
    first_word = stripped.split(maxsplit=1)[0].rstrip("(;")
    if first_word.upper() not in _DDL_DML_KEYWORDS:
        return False
    if _has_returning_clause(stripped):
        return False
    return True


class Cursor(_BaseCursor):
    """GizmoSQL cursor with automatic DDL/DML detection.

    ``execute()`` auto-detects DDL/DML statements and routes them through
    ``execute_update()`` for immediate server-side execution, matching the
    behavior of the GizmoSQL JDBC and ODBC drivers.

    ``execute_update()`` is still available for explicit DDL/DML execution.
    """

    def execute(self, operation, parameters=None):
        """Execute a query, auto-detecting DDL/DML for immediate execution.

        GizmoSQL uses lazy execution — ``GetFlightInfo`` only plans queries,
        and actual execution is deferred to ``DoGet`` (fetch).  For DDL/DML
        the statement would never execute unless the client fetches.

        This override detects DDL/DML by SQL keyword and routes it through
        ``execute_update()`` (the server's ``DoPut`` RPC) for immediate
        execution, matching the JDBC/ODBC driver pattern.

        ``INSERT/UPDATE/DELETE ... RETURNING`` statements take the regular
        ``GetFlightInfo`` → ``DoGet`` query path (since they produce a
        result set the ``DoPut`` rowcount-only path cannot carry), but the
        result is **eagerly materialized** here to ensure the underlying
        DML actually fires regardless of whether the caller fetches —
        otherwise GizmoSQL's lazy planning would no-op the statement.
        ``cursor.fetch_arrow_table()`` (and the other fetch APIs) then
        return the cached rows.

        For SELECT/WITH/SHOW and other read queries, the standard
        ``execute()`` path is used (GetFlightInfo → DoGet on fetch) without
        eager materialization — large result sets stream as usual.

        Args:
            operation: SQL query string or serialized Substrait plan (bytes).
            parameters: Optional bind parameters (sequence, dict, or Arrow data).

        Returns:
            This cursor (to enable method chaining).
        """
        if _is_ddl_dml(operation=operation) and parameters is None:
            # DDL/DML — execute immediately via DoPut RPC.
            self.adbc_statement.set_sql_query(query=operation)
            self._rowcount = self.adbc_statement.execute_update()
            self._results = None  # description returns None when _results is None
            self._last_query = operation
            return self

        # SELECT/WITH/SHOW and INSERT/UPDATE/DELETE...RETURNING.
        super().execute(operation=operation, parameters=parameters)

        # For DML with a RETURNING clause, eagerly materialize the result so
        # the underlying statement actually executes. Without this, the user
        # could call cursor.execute("INSERT ... RETURNING ...") and never
        # fetch — and GizmoSQL's lazy GetFlightInfo would mean the row never
        # lands in the table. We then swap _results for an in-memory iterator
        # so subsequent fetch_arrow_table()/fetchall()/etc. still work.
        if isinstance(operation, str) and _has_returning_clause(
            sql=_strip_sql_comments(sql=operation)
        ):
            try:
                cached = super().fetch_arrow_table()
            finally:
                # The underlying _RowIterator is now consumed; close it to
                # release any driver-side resources.
                if self._results is not None:
                    self._results.close()
            self._results = _CachedRowIterator(table=cached)
            self._rowcount = cached.num_rows
        return self

    def execute_update(self, query: str) -> int:
        """Execute a DDL/DML statement immediately and return the rows affected.

        This calls the ADBC statement's ``execute_update()`` method directly
        (the server's ``DoPutPreparedStatementUpdate`` RPC).  Unlike
        ``cursor.execute()``, this fires the statement immediately on the
        server **without requiring a fetch**, making it the preferred way to
        run DDL (``CREATE``, ``DROP``, ``ALTER``) and DML (``INSERT``,
        ``UPDATE``, ``DELETE``) statements with GizmoSQL's lazy-execution
        model.

        Args:
            query: The SQL DDL or DML statement to execute.

        Returns:
            The number of rows affected (``0`` for DDL statements that do not
            affect rows).

        Example::

            with conn.cursor() as cur:
                cur.execute_update("CREATE TABLE t (a INT)")
                rows = cur.execute_update("INSERT INTO t VALUES (1)")
                print(f"Rows affected: {rows}")
        """
        self.adbc_statement.set_sql_query(query)
        return self.adbc_statement.execute_update()


class Connection(_BaseConnection):
    """GizmoSQL connection that returns :class:`Cursor` instances."""

    # Cache and lock for adbc_get_info(). The Go ADBC Flight SQL driver has an
    # upstream bug (apache/arrow-adbc#1178) where concurrent adbc_get_info()
    # calls crash with "fatal error: concurrent map writes" due to an
    # unprotected map in DriverInfo. We call the underlying method exactly once
    # and cache the result.
    _get_info_lock = threading.Lock()
    _get_info_cache: Optional[Dict[Union[str, int], Any]] = None

    def adbc_get_info(self) -> Dict[Union[str, int], Any]:
        """Get metadata about the database and driver (thread-safe, cached)."""
        if self._get_info_cache is None:
            with self._get_info_lock:
                if self._get_info_cache is None:
                    Connection._get_info_cache = super().adbc_get_info()
        return self._get_info_cache

    def cursor(
        self,
        *,
        adbc_stmt_kwargs: Optional[dict[str, Any]] = None,
    ) -> Cursor:
        """Create a new :class:`Cursor` for querying the database."""
        cursor = Cursor(self, adbc_stmt_kwargs, dbapi_backend=self._backend)
        self._cursors.add(cursor)
        return cursor


def connect(
    uri: Optional[str] = None,
    *,
    profile: Optional[str] = None,
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

    At least one of ``uri`` or ``profile`` must be provided. When a
    connection profile supplies the server URI, ``uri`` may be omitted::

        # ~/.config/adbc/profiles/gizmosql_dev.toml (macOS:
        # ~/Library/Application Support/ADBC/Profiles/gizmosql_dev.toml)
        #
        #   profile_version = 1
        #   [Options]
        #   uri = "grpc+tls://localhost:31337"
        #   username = "user"
        #   password = "{{ env_var(GIZMOSQL_PASSWORD) }}"

        with gizmosql.connect(profile="gizmosql_dev") as conn:
            ...

    Args:
        uri: Flight SQL URI (e.g., ``"grpc+tls://localhost:31337"``).
            Optional if ``profile`` supplies the URI. A ``profile://<name>``
            URI is also accepted and is equivalent to ``profile=<name>``.
        profile: Name of an ADBC connection profile to load (a bare name
            resolved against the standard ADBC profile search paths —
            including ``$ADBC_PROFILE_PATH`` — or an absolute path to a
            ``.toml`` profile file). Options set explicitly in Python
            (``username``, ``password``, ``db_kwargs``, ...) override the
            profile's ``[Options]``. The profile does not need to specify a
            ``driver``: the Flight SQL driver bundled with this package is
            supplied automatically. See
            https://arrow.apache.org/adbc/current/format/connection_profiles.html
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
        A DBAPI 2.0 :class:`Connection` object.

    Raises:
        GizmoSQLOAuthError: If the OAuth flow fails.
        ValueError: If required parameters are missing for the chosen auth type,
            or if neither ``uri`` nor ``profile`` is provided.
    """
    if uri is None and profile is None:
        raise ValueError("Must provide at least one of 'uri' or 'profile'.")

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

    if profile is not None:
        db_kwargs.setdefault("profile", profile)

    if auth_type == "external":
        # Extract host from URI for OAuth discovery. With a profile-only
        # connection (or a profile:// URI) the server host isn't known
        # client-side, so an explicit oauth_url is required.
        if oauth_url is None and (uri is None or uri.startswith("profile://")):
            raise ValueError(
                "auth_type='external' with a connection profile requires either "
                "an explicit Flight SQL 'uri' or an 'oauth_url' for OAuth discovery."
            )
        host = _extract_host(uri) if uri is not None else ""
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
        raise ValueError(f"Invalid auth_type: {auth_type!r}. Must be 'password' or 'external'.")

    db = None
    conn = None
    try:
        if uri is not None:
            db = adbc_driver_flightsql.connect(uri, db_kwargs=db_kwargs)
        else:
            # Profile-only connection: the profile's [Options] supply the URI.
            # Pass the bundled Flight SQL driver explicitly so the profile
            # does not need a 'driver' entry (bare driver names are not
            # resolved inside Python site-packages by the driver manager).
            db = adbc_driver_manager.AdbcDatabase(
                driver=adbc_driver_flightsql._driver_path(), **db_kwargs
            )
        conn = adbc_driver_manager.AdbcConnection(db, **(conn_kwargs or {}))
        return Connection(db, conn, autocommit=autocommit)
    except Exception:
        if conn:
            conn.close()
        if db:
            db.close()
        raise


def execute_update(cursor: Cursor, query: str) -> int:
    """Execute a DDL/DML statement immediately and return the rows affected.

    .. deprecated::
        Use ``cursor.execute_update(query)`` instead.

    This is a backward-compatible wrapper.  New code should call
    ``cursor.execute_update(query)`` directly.

    Args:
        cursor: An open DBAPI 2.0 cursor obtained from ``connection.cursor()``.
        query: The SQL DDL or DML statement to execute.

    Returns:
        The number of rows affected (``0`` for DDL statements that do not
        affect rows).

    Example::

        with conn.cursor() as cur:
            rows = gizmosql.execute_update(cur, "INSERT INTO t VALUES (1)")
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
