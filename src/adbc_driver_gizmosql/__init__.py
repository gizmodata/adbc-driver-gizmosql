"""ADBC driver for GizmoSQL with OAuth/SSO support.

This package provides a lightweight Python wrapper around
``adbc-driver-flightsql`` that adds GizmoSQL-specific features,
including OAuth/SSO browser flow authentication.

Quick start::

    from adbc_driver_gizmosql import dbapi as gizmosql

    # Password authentication
    with gizmosql.connect("grpc+tls://localhost:31337",
                          username="user", password="pass",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print(cur.fetch_arrow_table())

    # OAuth/SSO authentication
    with gizmosql.connect("grpc+tls://localhost:31337",
                          auth_type="external",
                          tls_skip_verify=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_USER")
            print(cur.fetch_arrow_table())
"""

from __future__ import annotations

from adbc_driver_flightsql import ConnectionOptions, DatabaseOptions

from ._oauth import GizmoSQLOAuthError, OAuthResult, get_oauth_token
from ._version import __version__

__all__ = [
    "ConnectionOptions",
    "DatabaseOptions",
    "GizmoSQLOAuthError",
    "OAuthResult",
    "__version__",
    "get_oauth_token",
]
