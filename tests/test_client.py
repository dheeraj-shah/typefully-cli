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


class TestListRecentNullPublishedAt:
    """Entries with null/missing published_at are skipped, not TypeError."""

    def _make_client(self):
        client = TypefullyClient(api_key="test")
        client._social_sets_cache = [{"id": 1, "username": "a", "name": "A"}]
        return client

    def test_null_published_at_skipped(self):
        client = self._make_client()
        client.list_drafts = MagicMock(return_value={
            "results": [
                {"id": 1, "published_at": "2024-06-15T10:00:00Z"},
                {"id": 2, "published_at": None},
                {"id": 3, "published_at": "2024-06-10T10:00:00Z"},
            ]
        })
        results = client.list_recent(1, since="2024-06-01", until="2024-06-30")
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 3

    def test_missing_published_at_skipped(self):
        client = self._make_client()
        client.list_drafts = MagicMock(return_value={
            "results": [
                {"id": 1},
                {"id": 2, "published_at": "2024-06-15T10:00:00Z"},
            ]
        })
        results = client.list_recent(1, since="2024-06-01", until="2024-06-30")
        assert len(results) == 1
        assert results[0]["id"] == 2


class TestEnsureTagsPagination:
    """ensure_tags fetches all pages of tags, not just the first 50."""

    def test_paginates_beyond_50_tags(self):
        client = TypefullyClient(api_key="test")
        page1 = [{"name": f"tag-{i}"} for i in range(50)]
        page2 = [{"name": f"tag-{i}"} for i in range(50, 55)]

        def mock_list_tags(social_set_id, limit=50, offset=0):
            if offset == 0:
                return {"results": page1}
            return {"results": page2}

        client.list_tags = MagicMock(side_effect=mock_list_tags)
        client.create_tag = MagicMock()

        # tag-52 exists on page 2, should NOT be created
        warnings = client.ensure_tags(1, ["tag-52"])
        client.create_tag.assert_not_called()
        assert warnings == []

    def test_creates_tag_not_on_any_page(self):
        client = TypefullyClient(api_key="test")

        def mock_list_tags(social_set_id, limit=50, offset=0):
            if offset == 0:
                return {"results": [{"name": f"tag-{i}"} for i in range(50)]}
            return {"results": [{"name": f"tag-{i}"} for i in range(50, 55)]}

        client.list_tags = MagicMock(side_effect=mock_list_tags)
        client.create_tag = MagicMock()

        client.ensure_tags(1, ["brand-new"])
        client.create_tag.assert_called_once_with(1, "brand-new")
