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
    from conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

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


class TestExecuteUpdate:
    """Test execute_update() for DDL/DML that fires immediately."""

    def test_create_insert_query_drop(self, conn):
        from adbc_driver_gizmosql import dbapi as gizmosql

        with conn.cursor() as cur:
            # DDL — CREATE TABLE
            result = gizmosql.execute_update(
                cur, "CREATE TABLE test_exec_update (id INT, name VARCHAR)"
            )
            # DDL typically returns -1 (no row count)
            assert isinstance(result, int)

        try:
            with conn.cursor() as cur:
                # DML — INSERT single row
                rows = gizmosql.execute_update(
                    cur,
                    "INSERT INTO test_exec_update VALUES (1, 'alice')",
                )
                assert rows == 1

                # DML — INSERT another row
                rows = gizmosql.execute_update(
                    cur,
                    "INSERT INTO test_exec_update VALUES (2, 'bob')",
                )
                assert rows == 1

            # Verify the data was actually written
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name FROM test_exec_update ORDER BY id"
                )
                table = cur.fetch_arrow_table()
                assert table.num_rows == 2
                assert table.column("id")[0].as_py() == 1
                assert table.column("name")[1].as_py() == "bob"
        finally:
            # Clean up
            with conn.cursor() as cur:
                gizmosql.execute_update(cur, "DROP TABLE test_exec_update")

    def test_update_returns_rows_affected(self, conn):
        from adbc_driver_gizmosql import dbapi as gizmosql

        with conn.cursor() as cur:
            gizmosql.execute_update(
                cur, "CREATE TABLE test_eu_update (val INT)"
            )

        try:
            with conn.cursor() as cur:
                gizmosql.execute_update(
                    cur, "INSERT INTO test_eu_update VALUES (1)"
                )
                gizmosql.execute_update(
                    cur, "INSERT INTO test_eu_update VALUES (2)"
                )
                gizmosql.execute_update(
                    cur, "INSERT INTO test_eu_update VALUES (3)"
                )

            with conn.cursor() as cur:
                rows = gizmosql.execute_update(
                    cur, "DELETE FROM test_eu_update WHERE val >= 2"
                )
                assert rows == 2
        finally:
            with conn.cursor() as cur:
                gizmosql.execute_update(cur, "DROP TABLE test_eu_update")


class TestConnectionContextManager:
    """Test that the connection works properly as a context manager."""

    def test_fresh_connection(self, gizmosql_server, gizmosql_uri):
        from adbc_driver_gizmosql import dbapi as gizmosql
        from conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

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
