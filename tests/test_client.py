"""Tests for TypefullyClient account resolution and error handling."""

from unittest.mock import MagicMock

import httpx
import pytest

from typefully_cli.client import TypefullyClient
from typefully_cli.exceptions import AccountError, APIError


class TestAccountResolution:
    """Test account resolution logic (no real API calls)."""

    def _make_client_with_cache(self, sets):
        client = TypefullyClient(api_key="test_key")
        client._social_sets_cache = sets
        return client

    def test_resolve_by_numeric_id(self):
        client = self._make_client_with_cache([
            {"id": 123, "username": "foo", "name": "Foo"},
        ])
        assert client.resolve_account("123") == 123

    def test_resolve_by_username(self):
        client = self._make_client_with_cache([
            {"id": 123, "username": "MyBrand", "name": "My Brand Account"},
        ])
        assert client.resolve_account("mybrand") == 123

    def test_resolve_by_name(self):
        client = self._make_client_with_cache([
            {"id": 456, "username": "other", "name": "MyBrand"},
        ])
        assert client.resolve_account("mybrand") == 456

    def test_resolve_config_default(self):
        client = self._make_client_with_cache([
            {"id": 789, "username": "DefaultAcc", "name": "Default"},
        ])
        assert client.resolve_account(None, config_default="DefaultAcc") == 789

    def test_resolve_no_value_raises(self):
        client = self._make_client_with_cache([
            {"id": 1, "username": "a", "name": "A"},
        ])
        with pytest.raises(AccountError) as exc_info:
            client.resolve_account(None)
        assert "no_account" == exc_info.value.code

    def test_resolve_not_found_raises(self):
        client = self._make_client_with_cache([
            {"id": 1, "username": "a", "name": "A"},
        ])
        with pytest.raises(AccountError) as exc_info:
            client.resolve_account("nonexistent")
        assert "not found" in str(exc_info.value).lower()
        assert "Available accounts" in exc_info.value.hint

    def test_resolve_empty_sets_raises(self):
        client = self._make_client_with_cache([])
        with pytest.raises(AccountError) as exc_info:
            client.resolve_account("anything")
        assert "No social sets" in str(exc_info.value)

    def test_numeric_id_not_found_falls_through_to_name(self):
        client = self._make_client_with_cache([
            {"id": 100, "username": "999", "name": "Nine"},
        ])
        # "999" is not a valid ID but is a valid username
        assert client.resolve_account("999") == 100

    def test_priority_positional_over_config(self):
        client = self._make_client_with_cache([
            {"id": 1, "username": "alpha", "name": "Alpha"},
            {"id": 2, "username": "beta", "name": "Beta"},
        ])
        assert client.resolve_account("beta", config_default="alpha") == 2


class TestRequestErrorHandling:
    """Test that transport and JSON errors are wrapped into APIError."""

    def test_timeout_raises_api_error(self):
        client = TypefullyClient(api_key="test")
        client._client = MagicMock()
        client._client.request.side_effect = httpx.ReadTimeout("timed out")
        with pytest.raises(APIError) as exc_info:
            client._request("GET", "/test")
        assert "timed out" in str(exc_info.value).lower()

    def test_connect_error_raises_api_error(self):
        client = TypefullyClient(api_key="test")
        client._client = MagicMock()
        client._client.request.side_effect = httpx.ConnectError("connection refused")
        with pytest.raises(APIError) as exc_info:
            client._request("GET", "/test")
        assert "network error" in str(exc_info.value).lower()

    def test_invalid_json_raises_api_error(self):
        client = TypefullyClient(api_key="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_success = True
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        client._client = MagicMock()
        client._client.request.return_value = mock_resp
        with pytest.raises(APIError) as exc_info:
            client._request("GET", "/test")
        assert "invalid json" in str(exc_info.value).lower()
