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
    from conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

    from adbc_driver_gizmosql import dbapi as gizmosql

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


class TestExecuteAutoDetect:
    """Test cursor.execute() auto-detecting DDL/DML for immediate execution."""

    def test_create_insert_query_drop(self, conn):
        """execute() handles the full DDL/DML/SELECT lifecycle."""
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE test_auto_detect (id INT, name VARCHAR)")

        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO test_auto_detect VALUES (1, 'alice')")
                cur.execute("INSERT INTO test_auto_detect VALUES (2, 'bob')")

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, name FROM test_auto_detect ORDER BY id"
                )
                table = cur.fetch_arrow_table()
                assert table.num_rows == 2
                assert table.column("id")[0].as_py() == 1
                assert table.column("name")[1].as_py() == "bob"
        finally:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE test_auto_detect")

    def test_description_none_after_ddl(self, conn):
        """execute() returns None description for DDL (DBAPI 2.0 spec)."""
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE test_desc_ddl (id INT)")
        try:
            with conn.cursor() as cur:
                cur.execute("DROP TABLE test_desc_ddl")
                assert cur.description is None
        except Exception:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE IF EXISTS test_desc_ddl")
            raise

    def test_description_present_after_select(self, conn):
        """execute() returns column descriptions for SELECT."""
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS a, 'hello' AS b")
            assert cur.description is not None
            assert len(cur.description) == 2

    def test_chaining(self, conn):
        """execute() returns self for method chaining."""
        with conn.cursor() as cur:
            result = cur.execute("SELECT 1")
            assert result is cur


class TestExecuteUpdate:
    """Test cursor.execute_update() for explicit DDL/DML with rows-affected count."""

    def test_create_insert_query_drop(self, conn):
        with conn.cursor() as cur:
            # DDL — CREATE TABLE
            result = cur.execute_update(
                "CREATE TABLE test_exec_update (id INT, name VARCHAR)"
            )
            assert result == 0

        try:
            with conn.cursor() as cur:
                # DML — INSERT single row
                rows = cur.execute_update(
                    "INSERT INTO test_exec_update VALUES (1, 'alice')",
                )
                assert rows == 1

                # DML — INSERT another row
                rows = cur.execute_update(
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
                cur.execute_update("DROP TABLE test_exec_update")

    def test_update_returns_rows_affected(self, conn):
        with conn.cursor() as cur:
            cur.execute_update("CREATE TABLE test_eu_update (val INT)")

        try:
            with conn.cursor() as cur:
                cur.execute_update("INSERT INTO test_eu_update VALUES (1)")
                cur.execute_update("INSERT INTO test_eu_update VALUES (2)")
                cur.execute_update("INSERT INTO test_eu_update VALUES (3)")

            with conn.cursor() as cur:
                rows = cur.execute_update(
                    "DELETE FROM test_eu_update WHERE val >= 2"
                )
                assert rows == 2

            # Verify only the expected row survives
            with conn.cursor() as cur:
                cur.execute("SELECT val FROM test_eu_update ORDER BY val")
                table = cur.fetch_arrow_table()
                assert table.num_rows == 1
                assert table.column("val")[0].as_py() == 1
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_eu_update")

    def test_module_level_execute_update_backward_compat(self, conn):
        """Verify the module-level execute_update() shim still works."""
        from adbc_driver_gizmosql import dbapi as gizmosql

        with conn.cursor() as cur:
            result = gizmosql.execute_update(
                cur, "CREATE TABLE test_eu_compat (id INT)"
            )
            assert isinstance(result, int)

        try:
            with conn.cursor() as cur:
                rows = gizmosql.execute_update(
                    cur, "INSERT INTO test_eu_compat VALUES (1)"
                )
                assert rows == 1
        finally:
            with conn.cursor() as cur:
                gizmosql.execute_update(cur, "DROP TABLE test_eu_compat")


class TestBulkIngest:
    """Test ADBC bulk ingest (adbc_ingest) for loading Arrow data into tables."""

    def test_ingest_create(self, conn):
        """Test mode='create' — creates a new table and inserts data."""
        import pyarrow as pa

        table = pa.table({
            "id": [1, 2, 3],
            "name": ["alice", "bob", "charlie"],
        })

        with conn.cursor() as cur:
            cur.adbc_ingest("test_ingest_create", table, mode="create")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM test_ingest_create ORDER BY id")
                result = cur.fetch_arrow_table()
                assert result.num_rows == 3
                assert result.column("id").to_pylist() == [1, 2, 3]
                assert result.column("name").to_pylist() == ["alice", "bob", "charlie"]
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_ingest_create")

    def test_ingest_append(self, conn):
        """Test mode='append' — appends data to an existing table."""
        import pyarrow as pa

        with conn.cursor() as cur:
            cur.execute_update(
                "CREATE TABLE test_ingest_append (id BIGINT, val DOUBLE)"
            )

        try:
            batch1 = pa.table({"id": [1, 2], "val": [10.0, 20.0]})
            batch2 = pa.table({"id": [3, 4], "val": [30.0, 40.0]})

            with conn.cursor() as cur:
                cur.adbc_ingest("test_ingest_append", batch1, mode="append")
                cur.adbc_ingest("test_ingest_append", batch2, mode="append")

            with conn.cursor() as cur:
                cur.execute("SELECT id, val FROM test_ingest_append ORDER BY id")
                result = cur.fetch_arrow_table()
                assert result.num_rows == 4
                assert result.column("id").to_pylist() == [1, 2, 3, 4]
                assert result.column("val").to_pylist() == [10.0, 20.0, 30.0, 40.0]
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_ingest_append")

    def test_ingest_create_append(self, conn):
        """Test mode='create_append' — creates if needed, then appends."""
        import pyarrow as pa

        table = pa.table({"x": [100, 200]})

        # First call creates the table
        with conn.cursor() as cur:
            cur.adbc_ingest("test_ingest_ca", table, mode="create_append")

        try:
            # Second call appends to the existing table
            with conn.cursor() as cur:
                cur.adbc_ingest("test_ingest_ca", table, mode="create_append")

            with conn.cursor() as cur:
                cur.execute("SELECT x FROM test_ingest_ca ORDER BY x")
                result = cur.fetch_arrow_table()
                assert result.num_rows == 4
                assert result.column("x").to_pylist() == [100, 100, 200, 200]
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_ingest_ca")

    def test_ingest_replace(self, conn):
        """Test mode='replace' — drops and recreates the table."""
        import pyarrow as pa

        original = pa.table({"a": [1, 2, 3]})
        replacement = pa.table({"a": [99]})

        with conn.cursor() as cur:
            cur.adbc_ingest("test_ingest_replace", original, mode="create")

        try:
            with conn.cursor() as cur:
                cur.adbc_ingest("test_ingest_replace", replacement, mode="replace")

            with conn.cursor() as cur:
                cur.execute("SELECT a FROM test_ingest_replace")
                result = cur.fetch_arrow_table()
                assert result.num_rows == 1
                assert result.column("a")[0].as_py() == 99
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_ingest_replace")

    def test_ingest_record_batch(self, conn):
        """Test ingesting a single RecordBatch (not a full Table)."""
        import pyarrow as pa

        batch = pa.record_batch(
            {"id": [10, 20], "label": ["foo", "bar"]}
        )

        with conn.cursor() as cur:
            cur.adbc_ingest("test_ingest_rb", batch, mode="create")

        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id, label FROM test_ingest_rb ORDER BY id")
                result = cur.fetch_arrow_table()
                assert result.num_rows == 2
                assert result.column("id").to_pylist() == [10, 20]
                assert result.column("label").to_pylist() == ["foo", "bar"]
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_ingest_rb")


class TestReturningClause:
    """End-to-end tests for INSERT/UPDATE/DELETE ... RETURNING.

    Regression for issue #163: ``INSERT ... RETURNING`` was being routed
    through ``execute_update()`` (DoPut), which only returns a row count
    and discards the ``RETURNING`` rows. The cursor must instead take the
    regular query path so ``fetch_arrow_table()`` exposes the returned
    rows.
    """

    def test_insert_returning_yields_rows(self, conn):
        with conn.cursor() as cur:
            cur.execute_update(
                "CREATE SEQUENCE test_returning_seq; "
                "CREATE TABLE test_returning ("
                "    id INTEGER DEFAULT nextval('test_returning_seq') PRIMARY KEY,"
                "    name VARCHAR"
                ")"
            )

        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO test_returning (name) VALUES "
                    "('alice'), ('bob') RETURNING id, name"
                )
                # Description must reflect a real result set (was None before fix).
                assert cur.description is not None
                table = cur.fetch_arrow_table()
                assert table.num_rows == 2
                assert set(table.column("name").to_pylist()) == {"alice", "bob"}
                # IDs are sequence-generated; just verify both are non-null.
                ids = table.column("id").to_pylist()
                assert all(isinstance(i, int) for i in ids)
                assert len(set(ids)) == 2

            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE test_returning SET name = 'CAROL' "
                    "WHERE name = 'alice' RETURNING id, name"
                )
                table = cur.fetch_arrow_table()
                assert table.num_rows == 1
                assert table.column("name")[0].as_py() == "CAROL"

            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM test_returning WHERE name = 'bob' "
                    "RETURNING id"
                )
                table = cur.fetch_arrow_table()
                assert table.num_rows == 1
        finally:
            with conn.cursor() as cur:
                cur.execute_update(
                    "DROP TABLE test_returning; "
                    "DROP SEQUENCE test_returning_seq"
                )

    def test_insert_without_returning_still_uses_doput(self, conn):
        # Sanity check: a plain INSERT (no RETURNING) must still take the
        # execute_update path — i.e. cursor.description stays None and the
        # rowcount comes back populated. This guards against the carve-out
        # accidentally widening to all DML.
        with conn.cursor() as cur:
            cur.execute_update("CREATE TABLE test_no_returning (id INT)")
        try:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO test_no_returning VALUES (1), (2)")
                assert cur.description is None
                assert cur.rowcount == 2
        finally:
            with conn.cursor() as cur:
                cur.execute_update("DROP TABLE test_no_returning")


class TestConnectionContextManager:
    """Test that the connection works properly as a context manager."""

    def test_fresh_connection(self, gizmosql_server, gizmosql_uri):
        from conftest import GIZMOSQL_PASSWORD, GIZMOSQL_USERNAME

        from adbc_driver_gizmosql import dbapi as gizmosql

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
