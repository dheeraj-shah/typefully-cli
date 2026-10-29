"""Offline contract tests for the public request schema and new media operations."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from typefully_cli.cli import cli
from typefully_cli.client import TypefullyClient
from typefully_cli.exceptions import TypefullyError
from typefully_cli.payloads import SCHEMA_FILE, validate_payload


def payload(platform="x", **post):
    return {"platforms": {platform: {"enabled": True, "posts": [{"text": "hi", **post}]}}}


@pytest.mark.parametrize(
    "platform", ["x", "linkedin", "threads", "bluesky", "mastodon", "substack"]
)
def test_platform_schema(platform):
    assert validate_payload(payload(platform), "create")


def test_null_false_arrays_and_comment_markers_preserved():
    body = payload(reply_settings=None, subscribers_only=False)
    body.update(draft_title=None, tags=[], publish_at=None, force_overwrite_comments=False)
    body["platforms"]["x"]["posts"][0]["text"] = "[comment:123] keep this"
    assert validate_payload(body, "update") is body


@pytest.mark.parametrize(
    "body",
    [
        [],
        None,
        "text",
        {},
        {"unexpected": True},
        payload(reply_settings="everyone"),
        payload(subscribers_only="false"),
        payload("linkedin", linkedin_reshare_target="x" * 2049),
        {**payload(), "publish_at": "tomorrow"},
        {**payload(), "publish_at": "2026-11-01T10:00:00"},
        {**payload(), "publish_at": "now", "plan_at": "next-free-slot"},
        {**payload(), "tags": ["x"] * 11},
    ],
)
def test_invalid_payload(body):
    with pytest.raises(TypefullyError):
        validate_payload(body, "create")


def test_validate_only_no_auth_or_transport():
    with patch("typefully_cli.cli._get_client_and_console") as get:
        result = CliRunner().invoke(
            cli,
            ["draft-payload", "create", "--file", "-", "--validate-only"],
            input=json.dumps(payload()),
        )
    assert result.exit_code == 0, result.output
    get.assert_not_called()


@pytest.mark.parametrize(
    "args,body",
    [(["update"], payload()), (["create", "--draft-id", "5"], payload()), (["create"], "not json")],
)
def test_invalid_input_no_transport(args, body):
    with patch("typefully_cli.cli._get_client_and_console") as get:
        result = CliRunner().invoke(
            cli,
            ["draft-payload", *args, "--file", "-"],
            input=body if isinstance(body, str) else json.dumps(body),
        )
    assert result.exit_code != 0
    get.assert_not_called()


def mock_client():
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 7
    return client


@pytest.mark.parametrize("action", ["create", "update"])
def test_payload_transport_unchanged(action):
    body = payload(subscribers_only=False, reply_settings=None)
    client = mock_client()
    client.create_draft.return_value = {"id": 9}
    client.update_draft.return_value = {"id": 9}
    extra = ["--draft-id", "9"] if action == "update" else []
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(
            cli, ["draft-payload", action, "--file", "-", *extra], input=json.dumps(body)
        )
    assert result.exit_code == 0, result.output
    if action == "create":
        client.create_draft.assert_called_once_with(7, body)
    else:
        client.update_draft.assert_called_once_with(7, 9, body)


@pytest.mark.parametrize(
    "args,expected",
    [
        (["--clear-alt-text"], None),
        (["--alt-text", ""], ""),
        (["--alt-text", "A red car"], "A red car"),
    ],
)
def test_media_update(args, expected):
    client = mock_client()
    client.update_media.return_value = {"id": "abc"}
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(cli, ["media-update", "abc", *args])
    assert result.exit_code == 0, result.output
    client.update_media.assert_called_once_with(7, "abc", expected)


def test_media_client_exact_routes():
    client = TypefullyClient(api_key="offline-test")
    client._request = MagicMock(return_value={})
    client.request_upload(7, "a.png", "A picture")
    client._request.assert_called_with(
        "POST", "/social-sets/7/media/upload", json={"file_name": "a.png", "alt_text": "A picture"}
    )
    client.update_media(7, "abc", None)
    client._request.assert_called_with("PATCH", "/social-sets/7/media/abc", json={"alt_text": None})
    client.close() if hasattr(client, "close") else client._client.close()


def test_accounts_pagination_cache():
    client = TypefullyClient(api_key="offline-test")
    client._request = MagicMock(
        side_effect=[
            {"results": [{"id": n} for n in range(50)]},
            {"results": [{"id": 51, "username": "last"}]},
        ]
    )
    assert len(client.get_social_sets()) == 51
    assert client.resolve_account("last") == 51
    assert client._request.call_count == 2
    client._request.assert_called_with("GET", "/social-sets", params={"limit": 50, "offset": 50})
    client._client.close()


def test_snapshot_vocabulary_supported():
    allowed = {
        "$ref",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "default",
        "description",
        "enum",
        "examples",
        "format",
        "if",
        "items",
        "maxItems",
        "maxLength",
        "properties",
        "required",
        "then",
        "title",
        "type",
    }

    def walk(schema):
        assert set(schema) <= allowed
        for key, value in schema.items():
            if key == "properties":
                for child in value.values():
                    walk(child)
            elif key in {"if", "then", "items"}:
                walk(value)
            elif key in {"anyOf", "allOf"}:
                for child in value:
                    walk(child)

    for schema in json.loads(SCHEMA_FILE.read_text())["schemas"].values():
        walk(schema)


def test_article_create_and_cover_only_patch():
    body = {"platforms": {"x_article": {"content_markdown": "# Title\n\nBody"}}}
    assert validate_payload(body, "create") is body
    assert validate_payload({"platforms": {"x_article": {"cover_media_id": None}}}, "update")
    with pytest.raises(TypefullyError):
        validate_payload({"platforms": {"x_article": {}}}, "create")
    with pytest.raises(TypefullyError):
        validate_payload({"platforms": {"x_article": {}, "x": {"enabled": False}}}, "update")


def test_multiple_tag_filters():
    client = mock_client()
    client.list_drafts.return_value = {"results": []}
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(cli, ["drafts", "--tag", "one", "--tag", "two", "--json"])
    assert result.exit_code == 0, result.output
    assert client.list_drafts.call_args.kwargs["tag"] == ["one", "two"]


def test_negative_offset_rejected():
    result = CliRunner().invoke(cli, ["drafts", "--offset", "-1"])
    assert result.exit_code == 2
