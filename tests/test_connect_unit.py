"""Unit tests for the dbapi connect function (no Docker required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adbc_driver_gizmosql._oauth import OAuthResult


class TestConnect:
    """Tests for dbapi.connect()."""

    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_password_auth(self, mock_connect):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = connect(
            "grpc+tls://localhost:31337",
            username="myuser",
            password="mypass",
            tls_skip_verify=True,
        )

        assert result == mock_conn
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["db_kwargs"]["username"] == "myuser"
        assert call_kwargs["db_kwargs"]["password"] == "mypass"
        assert "adbc.flight.sql.client_option.tls_skip_verify" in call_kwargs["db_kwargs"]

    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_password_auth_no_tls_skip(self, mock_connect):
        from adbc_driver_gizmosql.dbapi import connect

        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        connect(
            "grpc+tls://localhost:31337",
            username="myuser",
            password="mypass",
        )

        call_kwargs = mock_connect.call_args[1]
        assert "adbc.flight.sql.client_option.tls_skip_verify" not in call_kwargs["db_kwargs"]

    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_external_auth(self, mock_connect, mock_oauth):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(
            token="eyJ-id-token-from-idp",
            session_uuid="test-uuid",
        )
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        result = connect(
            "grpc+tls://localhost:31337",
            auth_type="external",
            tls_skip_verify=True,
        )

        assert result == mock_conn
        mock_oauth.assert_called_once_with(
            host="localhost",
            port=31339,
            tls_skip_verify=True,
            timeout=300,
            open_browser=True,
            oauth_url=None,
        )
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["db_kwargs"]["username"] == "token"
        assert call_kwargs["db_kwargs"]["password"] == "eyJ-id-token-from-idp"

    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_external_auth_custom_oauth_port(self, mock_connect, mock_oauth):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(token="jwt", session_uuid="uuid")
        mock_connect.return_value = MagicMock()

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

    @patch("adbc_driver_gizmosql.dbapi.get_oauth_token")
    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_external_auth_explicit_oauth_url(self, mock_connect, mock_oauth):
        from adbc_driver_gizmosql.dbapi import connect

        mock_oauth.return_value = OAuthResult(token="jwt", session_uuid="uuid")
        mock_connect.return_value = MagicMock()

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

    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_db_kwargs_passthrough(self, mock_connect):
        from adbc_driver_gizmosql.dbapi import connect

        mock_connect.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            username="user",
            password="pass",
            db_kwargs={"custom_option": "custom_value"},
        )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["db_kwargs"]["custom_option"] == "custom_value"
        assert call_kwargs["db_kwargs"]["username"] == "user"

    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_conn_kwargs_passthrough(self, mock_connect):
        from adbc_driver_gizmosql.dbapi import connect

        mock_connect.return_value = MagicMock()

        connect(
            "grpc+tls://localhost:31337",
            username="user",
            password="pass",
            conn_kwargs={"conn_option": "conn_value"},
        )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["conn_kwargs"]["conn_option"] == "conn_value"

    @patch("adbc_driver_gizmosql.dbapi._flightsql_dbapi.connect")
    def test_autocommit_default_true(self, mock_connect):
        from adbc_driver_gizmosql.dbapi import connect

        mock_connect.return_value = MagicMock()

        connect("grpc+tls://localhost:31337", username="u", password="p")

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["autocommit"] is True


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
