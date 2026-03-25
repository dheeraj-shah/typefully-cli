"""Tests for TypefullyClient account resolution."""

import pytest
from typefully_cli.client import TypefullyClient
from typefully_cli.exceptions import AccountError


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
