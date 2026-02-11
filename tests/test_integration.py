"""Integration tests against a running GizmoSQL Docker container.

These tests require Docker to be running and are marked with
``@pytest.mark.integration``. Skip them with:
    pytest -m "not integration"
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def conn(gizmosql_server, gizmosql_uri):
    """Create a DBAPI connection to the test GizmoSQL server."""
    from adbc_driver_gizmosql import dbapi as gizmosql
    from tests.conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

    with gizmosql.connect(
        gizmosql_uri,
        username=GIZMOSQL_USERNAME,
        password=GIZMOSQL_PASSWORD,
        tls_skip_verify=True,
    ) as connection:
        yield connection


class TestPasswordAuth:
    """Test password-based authentication and basic queries."""

    def test_select_one(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS value")
            table = cur.fetch_arrow_table()
            assert table.num_rows == 1
            assert table.column("value")[0].as_py() == 1

    def test_gizmosql_version(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT GIZMOSQL_VERSION() AS version")
            table = cur.fetch_arrow_table()
            assert table.num_rows == 1
            version = table.column("version")[0].as_py()
            assert isinstance(version, str)
            assert len(version) > 0

    def test_parameterized_query(self, conn):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT n_nationkey, n_name FROM nation WHERE n_nationkey = ?",
                parameters=[24],
            )
            table = cur.fetch_arrow_table()
            assert table.num_rows == 1
            assert table.column("n_nationkey")[0].as_py() == 24

    def test_fetch_arrow_table_type(self, conn):
        import pyarrow as pa

        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS a, 'hello' AS b")
            table = cur.fetch_arrow_table()
            assert isinstance(table, pa.Table)
            assert table.schema.names == ["a", "b"]

    def test_multiple_rows(self, conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM nation ORDER BY n_nationkey LIMIT 5")
            table = cur.fetch_arrow_table()
            assert table.num_rows == 5


class TestConnectionContextManager:
    """Test that the connection works properly as a context manager."""

    def test_fresh_connection(self, gizmosql_server, gizmosql_uri):
        from adbc_driver_gizmosql import dbapi as gizmosql
        from tests.conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

        with gizmosql.connect(
            gizmosql_uri,
            username=GIZMOSQL_USERNAME,
            password=GIZMOSQL_PASSWORD,
            tls_skip_verify=True,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 42 AS answer")
                table = cur.fetch_arrow_table()
                assert table.column("answer")[0].as_py() == 42
