"""Unit tests for the dbapi connect function (no Docker required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adbc_driver_gizmosql._oauth import OAuthResult

# All tests need to mock the three layers that connect() calls internally:
#   1. adbc_driver_flightsql.connect  → creates the ADBC database
#   2. adbc_driver_manager.AdbcConnection  → wraps it in a connection
#   3. Connection  → our DBAPI wrapper
_PATCH_DB = "adbc_driver_gizmosql.dbapi.adbc_driver_flightsql.connect"
_PATCH_CONN = "adbc_driver_gizmosql.dbapi.adbc_driver_manager.AdbcConnection"
_PATCH_CLS = "adbc_driver_gizmosql.dbapi.Connection"


class TestConnect:
    """Tests for dbapi.connect()."""

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    def test_password_auth(self, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn_cls.return_value = MagicMock()

        result = connect(
            "grpc+tls://localhost:31337",
            username="myuser",
            password="mypass",
            tls_skip_verify=True,
        )

        assert result == mock_conn_cls.return_value
        mock_db_connect.assert_called_once()
        db_kwargs = mock_db_connect.call_args[1]["db_kwargs"]
        assert db_kwargs["username"] == "myuser"
        assert db_kwargs["password"] == "mypass"
        assert "adbc.flight.sql.client_option.tls_skip_verify" in db_kwargs

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    def test_password_auth_no_tls_skip(self, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn_cls.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            username="myuser",
            password="mypass",
        )

        db_kwargs = mock_db_connect.call_args[1]["db_kwargs"]
        assert "adbc.flight.sql.client_option.tls_skip_verify" not in db_kwargs

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    def test_external_auth(self, mock_oauth, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(
            token="eyJ-id-token-from-idp",
            session_uuid="test-uuid",
        )
        mock_conn_cls.return_value = MagicMock()

        result = connect(
            "grpc+tls://localhost:31337",
            auth_type="external",
            tls_skip_verify=True,
        )

        assert result == mock_conn_cls.return_value
        mock_oauth.assert_called_once_with(
            host="localhost",
            port=31339,
            tls_skip_verify=True,
            timeout=300,
            open_browser=True,
            oauth_url=None,
        )
        db_kwargs = mock_db_connect.call_args[1]["db_kwargs"]
        assert db_kwargs["username"] == "token"
        assert db_kwargs["password"] == "eyJ-id-token-from-idp"

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    def test_external_auth_custom_oauth_port(
        self, mock_oauth, mock_db_connect, mock_adbc_conn, mock_conn_cls
    ):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(token="jwt", session_uuid="uuid")
        mock_conn_cls.return_value = MagicMock()

        connect(
            "grpc+tls://myserver.example.com:31337",
            auth_type="external",
            oauth_port=8443,
            oauth_tls_skip_verify=False,
            tls_skip_verify=True,
        )

        mock_oauth.assert_called_once_with(
            host="myserver.example.com",
            port=8443,
            tls_skip_verify=False,
            timeout=300,
            open_browser=True,
            oauth_url=None,
        )

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    def test_external_auth_explicit_oauth_url(
        self, mock_oauth, mock_db_connect, mock_adbc_conn, mock_conn_cls
    ):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(token="jwt", session_uuid="uuid")
        mock_conn_cls.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            auth_type="external",
            oauth_url="https://oauth.example.com:9999",
        )

        mock_oauth.assert_called_once()
        assert mock_oauth.call_args[1]["oauth_url"] == "https://oauth.example.com:9999"

    def test_invalid_auth_type(self):
        from adbc_driver_gizmosql.dbapi import connect

        with pytest.raises(ValueError, match="Invalid auth_type"):
            connect("grpc+tls://localhost:31337", auth_type="kerberos")

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    def test_db_kwargs_passthrough(self, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn_cls.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            username="user",
            password="pass",
            db_kwargs={"custom_option": "custom_value"},
        )

        db_kwargs = mock_db_connect.call_args[1]["db_kwargs"]
        assert db_kwargs["custom_option"] == "custom_value"
        assert db_kwargs["username"] == "user"

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    def test_conn_kwargs_passthrough(self, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn_cls.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            username="user",
            password="pass",
            conn_kwargs={"conn_option": "conn_value"},
        )

        # conn_kwargs are unpacked into AdbcConnection
        mock_adbc_conn.assert_called_once_with(
            mock_db_connect.return_value,
            conn_option="conn_value",
        )

    @patch(_PATCH_CLS)
    @patch(_PATCH_CONN)
    @patch(_PATCH_DB)
    def test_autocommit_default_true(self, mock_db_connect, mock_adbc_conn, mock_conn_cls):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn_cls.return_value = MagicMock()

        connect("grpc+tls://localhost:31337", username="u", password="p")

        mock_conn_cls.assert_called_once_with(
            mock_db_connect.return_value,
            mock_adbc_conn.return_value,
            autocommit=True,
        )


class TestExecuteUpdate:
    """Tests for the module-level execute_update() backward-compat shim."""

    def test_execute_update_calls_adbc_statement(self):
        from adbc_driver_gizmosql.dbapi import execute_update

        mock_cursor = MagicMock()
        mock_cursor.adbc_statement.execute_update.return_value = 42

        result = execute_update(mock_cursor, "INSERT INTO t VALUES (1)")

        mock_cursor.adbc_statement.set_sql_query.assert_called_once_with("INSERT INTO t VALUES (1)")
        mock_cursor.adbc_statement.execute_update.assert_called_once()
        assert result == 42

    def test_execute_update_ddl_returns_int(self):
        from adbc_driver_gizmosql.dbapi import execute_update

        mock_cursor = MagicMock()
        mock_cursor.adbc_statement.execute_update.return_value = 0

        result = execute_update(mock_cursor, "CREATE TABLE t (a INT)")

        mock_cursor.adbc_statement.set_sql_query.assert_called_once_with("CREATE TABLE t (a INT)")
        assert result == 0

    def test_execute_update_propagates_exception(self):
        from adbc_driver_gizmosql.dbapi import execute_update

        mock_cursor = MagicMock()
        mock_cursor.adbc_statement.execute_update.side_effect = RuntimeError("server error")

        with pytest.raises(RuntimeError, match="server error"):
            execute_update(mock_cursor, "DROP TABLE nonexistent")


class TestIsDdlDml:
    """Tests for _is_ddl_dml() SQL keyword detection."""

    def test_create_table(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("CREATE TABLE t (a INT)") is True

    def test_drop_table(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("DROP TABLE t") is True

    def test_insert(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("INSERT INTO t VALUES (1)") is True

    def test_update(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("UPDATE t SET a = 1") is True

    def test_delete(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("DELETE FROM t WHERE a = 1") is True

    def test_alter(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("ALTER TABLE t ADD COLUMN b INT") is True

    def test_select_is_not_ddl_dml(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("SELECT 1") is False

    def test_with_cte_is_not_ddl_dml(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("WITH cte AS (SELECT 1) SELECT * FROM cte") is False

    def test_show_is_not_ddl_dml(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("SHOW TABLES") is False

    def test_leading_whitespace(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("   CREATE TABLE t (a INT)") is True

    def test_lowercase(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("create table t (a INT)") is True

    def test_mixed_case(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("Create Table t (a INT)") is True

    def test_empty_string(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("") is False

    def test_bytes_not_ddl_dml(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml(b"CREATE TABLE t (a INT)") is False

    def test_truncate(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("TRUNCATE TABLE t") is True

    def test_merge(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("MERGE INTO t USING s ON t.id = s.id") is True

    def test_copy(self):
        from adbc_driver_gizmosql.dbapi import _is_ddl_dml

        assert _is_ddl_dml("COPY t FROM '/tmp/data.csv'") is True


class TestCursorExecute:
    """Tests for Cursor.execute() auto-detection of DDL/DML."""

    def test_execute_ddl_calls_execute_update(self):
        """DDL is routed through execute_update (DoPut), not super().execute()."""
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()
        cursor.adbc_statement.execute_update.return_value = 0

        result = Cursor.execute(cursor, "CREATE TABLE t (a INT)")

        cursor.adbc_statement.set_sql_query.assert_called_once_with("CREATE TABLE t (a INT)")
        cursor.adbc_statement.execute_update.assert_called_once()
        assert cursor._results is None
        assert result is cursor

    def test_execute_insert_calls_execute_update(self):
        """DML is routed through execute_update."""
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()
        cursor.adbc_statement.execute_update.return_value = 1

        result = Cursor.execute(cursor, "INSERT INTO t VALUES (1)")

        cursor.adbc_statement.set_sql_query.assert_called_once_with("INSERT INTO t VALUES (1)")
        cursor.adbc_statement.execute_update.assert_called_once()
        assert cursor._rowcount == 1
        assert result is cursor

    @patch("adbc_driver_flightsql.dbapi.Cursor.execute")
    def test_execute_select_uses_standard_path(self, mock_super_execute):
        """SELECT uses the standard lazy-execution path (super().execute)."""
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()

        result = Cursor.execute(cursor, "SELECT 1")

        mock_super_execute.assert_called_once_with("SELECT 1", None)
        cursor.adbc_statement.execute_update.assert_not_called()
        assert result is cursor

    @patch("adbc_driver_flightsql.dbapi.Cursor.execute")
    def test_execute_with_parameters_uses_standard_path(self, mock_super_execute):
        """DDL/DML keywords with parameters use the standard path (parameterized query)."""
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()

        result = Cursor.execute(cursor, "INSERT INTO t VALUES (?)", parameters=[1])

        mock_super_execute.assert_called_once_with("INSERT INTO t VALUES (?)", [1])
        cursor.adbc_statement.execute_update.assert_not_called()
        assert result is cursor


class TestCursorExecuteUpdate:
    """Tests for Cursor.execute_update() method."""

    def test_execute_update_calls_adbc_statement(self):
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()
        cursor.adbc_statement.execute_update.return_value = 3

        # Call the real method on the mock instance
        result = Cursor.execute_update(cursor, "INSERT INTO t VALUES (1)")

        cursor.adbc_statement.set_sql_query.assert_called_once_with("INSERT INTO t VALUES (1)")
        cursor.adbc_statement.execute_update.assert_called_once()
        assert result == 3

    def test_execute_update_ddl(self):
        from adbc_driver_gizmosql.dbapi import Cursor

        cursor = MagicMock(spec=Cursor)
        cursor.adbc_statement = MagicMock()
        cursor.adbc_statement.execute_update.return_value = 0

        result = Cursor.execute_update(cursor, "CREATE TABLE t (a INT)")

        assert result == 0


class TestExtractHost:
    """Tests for URI host extraction."""

    def test_grpc_tls(self):
        from adbc_driver_gizmosql.dbapi import _extract_host

        assert _extract_host("grpc+tls://localhost:31337") == "localhost"

    def test_grpc_plain(self):
        from adbc_driver_gizmosql.dbapi import _extract_host

        assert _extract_host("grpc://myhost:31337") == "myhost"

    def test_hostname_with_domain(self):
        from adbc_driver_gizmosql.dbapi import _extract_host

        assert _extract_host("grpc+tls://gizmosql.example.com:31337") == "gizmosql.example.com"

    def test_no_port(self):
        from adbc_driver_gizmosql.dbapi import _extract_host

        assert _extract_host("grpc+tls://localhost") == "localhost"

    def test_grpc_tcp(self):
        from adbc_driver_gizmosql.dbapi import _extract_host

        assert _extract_host("grpc+tcp://192.168.1.1:31337") == "192.168.1.1"
