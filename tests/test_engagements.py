"""Offline coverage of engagement routes and the CLI output contract."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from click.testing import CliRunner

from typefully_cli.cli import cli
from typefully_cli.client import TypefullyClient
from typefully_cli.config import Config


@pytest.mark.parametrize(
    ("args", "method", "suffix", "payload", "status", "body", "expected"),
    [
        (["list", "12"], "GET", "engagements", None, 200, {"results": []}, {"results": []}),
        (["parent", "12"], "GET", "parent", None, 200, {"draft_id": 7}, {"draft_id": 7}),
        (["create", "12", "42", "--offset-seconds", "0"], "POST", "engagements",
         {"draft_id": 42, "offset_seconds": 0, "engagement_kind": "quote"},
         201, {"draft_id": 42}, {"draft_id": 42}),
        (["update", "12", "42", "--offset-seconds", "31536000"], "PATCH", "engagements/42",
         {"offset_seconds": 31536000}, 200, {"draft_id": 42}, {"draft_id": 42}),
        (["detach", "12", "42"], "DELETE", "engagements/42", None, 204, None, {"detached": 42}),
    ],
)
def test_engagement_request(args, method, suffix, payload, status, body, expected):
    client = TypefullyClient(api_key="offline")
    client._client.close()

    def handler(request):
        assert request.method == method
        assert request.url.path == "/v2/social-sets/3/drafts/12/" + suffix
        assert (json.loads(request.content) if request.content else None) == payload
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    client._client = httpx.Client(
        base_url=TypefullyClient.BASE_URL, transport=httpx.MockTransport(handler)
    )
    client._social_sets_cache = [{"id": 3, "name": "Example"}]
    with patch("typefully_cli.cli._get_client_and_console",
               return_value=(client, MagicMock(), Config())):
        result = CliRunner().invoke(cli, ["engagements", *args, "--account", "3", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ok": True, "data": expected}


@pytest.mark.parametrize(
    "args",
    [
        ["create", "7", "42", "--offset-seconds", "-1"],
        ["update", "7", "42", "--offset-seconds", "31536001"],
        ["create", "7", "7", "--offset-seconds", "0"],
    ],
)
def test_invalid_engagement_input_fails_before_auth(args):
    with patch("typefully_cli.cli._get_client_and_console") as get_client:
        result = CliRunner().invoke(cli, ["engagements", *args, "--json"])
    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["error"]["code"] == "invalid_input"
    get_client.assert_not_called()
