"""Offline regressions for carried-over Typefully behavior gaps."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from typefully_cli.cli import cli, _build_draft_payload
from typefully_cli.client import TypefullyClient
from typefully_cli.config import Config
from typefully_cli.console import Console
from typefully_cli.exceptions import APIError, TypefullyError


def runner():
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        return CliRunner()


def client_with_tags(tags, created=None):
    client = TypefullyClient(api_key="offline")
    client.list_tags = MagicMock(return_value={"results": tags})
    client.create_tag = MagicMock(return_value=created or {"name": "New Tag", "slug": "opaque-72"})
    return client


def test_resolver_prefers_exact_slug_and_maps_names_without_guessing():
    with client_with_tags([
        {"name": "Release Notes", "slug": "server-id-91"},
        {"name": "server-id-91", "slug": "different-id"},
    ]) as client:
        resolved = client.resolve_tag_slugs(1, ["Release Notes", "release notes", "server-id-91"])
        assert resolved == {
            "Release Notes": "server-id-91", "release notes": "server-id-91",
            "server-id-91": "server-id-91",
        }
        client.create_tag.assert_not_called()


def test_resolver_paginates_then_reuses_created_authoritative_slug():
    tags = [{"name": "Tag " + str(n), "slug": "tag-" + str(n)} for n in range(50)]
    with client_with_tags([]) as client:
        client.list_tags.side_effect = [
            {"results": tags, "next": "unused-url"},
            {"results": [{"name": "Last Page", "slug": "last-opaque"}], "next": None},
        ]
        result = client.resolve_tag_slugs(1, ["Last Page", "New Tag", "new tag", "New Tag"])
        assert result == {
            "Last Page": "last-opaque", "New Tag": "opaque-72", "new tag": "opaque-72",
        }
        client.list_tags.assert_called_with(1, limit=50, offset=50)
        client.create_tag.assert_called_once_with(1, "New Tag")


@pytest.mark.parametrize("created", [{}, {"name": "New Tag"}, {"slug": 123}])
def test_resolver_rejects_missing_or_invalid_created_slug(created):
    with client_with_tags([]) as client:
        client.create_tag.return_value = created
        with pytest.raises(TypefullyError) as caught:
            client.resolve_tag_slugs(1, ["New Tag"])
        assert caught.value.code == "tag_resolution_failed"


def test_ensure_tags_retains_warning_list_contract():
    with client_with_tags([]) as client:
        client.create_tag.side_effect = APIError(403, "not allowed")
        assert client.ensure_tags(1, ["New Tag"]) == ["Could not create tag 'New Tag'"]


@pytest.mark.parametrize("command", ["draft", "thread", "update", "batch"])
@pytest.mark.parametrize("fail", [False, True])
def test_all_tag_call_sites_resolve_and_fail_before_draft_mutation(command, fail, tmp_path):
    client = client_with_tags([{"name": "Release Notes", "slug": "not-predictable-17"}])
    client.resolve_account = MagicMock(return_value=1)
    client.create_draft = MagicMock(return_value={"id": 2, "status": "draft"})
    client.update_draft = MagicMock(return_value={"id": 2, "status": "draft"})
    client.rate_delay = MagicMock()
    if fail:
        client.create_tag.side_effect = APIError(403, '{"code":"FORBIDDEN"}')
    values = ["Release Notes", "release notes", "not-predictable-17", "New Tag"]
    flags = [item for value in values for item in ("--tag", value)]
    if command == "draft":
        args = ["draft", "Hello", *flags]
    elif command == "thread":
        args = ["thread", "One", "Two", *flags]
    elif command == "update":
        args = ["update", "2", "--title", "New title", *flags]
    else:
        path = tmp_path / "batch.txt"
        path.write_text("First post\n---\nSecond post\n")
        args = ["batch", str(path), *flags]
    with client, patch("typefully_cli.cli._get_client_and_console",
                       return_value=(client, Console(quiet=True), Config(default_account="offline"))):
        result = runner().invoke(cli, [*args, "--json", "--quiet"])
    if fail:
        assert result.exit_code == 2, result.output
        client.create_draft.assert_not_called()
        client.update_draft.assert_not_called()
        assert json.loads(result.stderr)["error"]["status"] == 403
    else:
        assert result.exit_code == 0, result.output
        calls = client.update_draft.call_args_list if command == "update" else client.create_draft.call_args_list
        assert len(calls) == (2 if command == "batch" else 1)
        for call in calls:
            body = call.args[2] if command == "update" else call.args[1]
            assert body["tags"] == ["not-predictable-17", "opaque-72"]
        client.create_tag.assert_called_once_with(1, "New Tag")


@pytest.mark.parametrize("action", ["draft", "update"])
@pytest.mark.parametrize("options", [
    ["--media", "media-id"], ["--paid-partnership"], ["--made-with-ai"],
    ["--hide-link-preview"], ["--community", "123"], ["--quote-post-url", "https://x.com/a/status/1"],
    ["--linkedin-first-comment", "Hi"], ["--no-subscribers-only"], ["--reply-settings", "null"],
    ["--share-with-followers"], ["--all"], ["--linkedin"],
])
def test_article_post_options_rejected_before_auth_or_requests(action, options):
    args = [action, *(["2"] if action == "update" else []),
            "--platform", "x_article", "--content-markdown", "# Title\n\nBody", *options]
    with patch("typefully_cli.cli._get_client_and_console") as auth:
        result = runner().invoke(cli, args)
    assert result.exit_code == 1, result.output
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    auth.assert_not_called()


@pytest.mark.parametrize("action", ["draft", "update"])
def test_article_file_and_text_rejected_before_auth(action, tmp_path):
    file = tmp_path / "post.txt"
    file.write_text("Post content")
    for extra in (["--file", str(file)], ["Post text"]):
        args = [action, *(["2"] if action == "update" else []),
                "--platform", "x_article", "--content-markdown", "# Title", *extra]
        with patch("typefully_cli.cli._get_client_and_console") as auth:
            result = runner().invoke(cli, args)
        assert result.exit_code == 1, result.output
        auth.assert_not_called()


def test_article_update_append_and_create_reply_rejected_before_auth():
    for args in [
        ["update", "2", "--platform", "x_article", "--cover-media-id", "null", "--append"],
        ["draft", "--platform", "x_article", "--content-markdown", "# Title",
         "--reply-to", "https://x.com/a/status/1"],
    ]:
        with patch("typefully_cli.cli._get_client_and_console") as auth:
            result = runner().invoke(cli, args)
        assert result.exit_code == 1
        auth.assert_not_called()


def test_article_builder_rejects_dropped_media_but_retains_valid_cover():
    with pytest.raises(TypefullyError):
        _build_draft_payload(posts_text=[], platforms=["x_article"],
                             content_markdown="# Title", media="id")
    body = _build_draft_payload(posts_text=[], platforms=["x_article"],
                                content_markdown="# Title", cover_media_id="cover")
    assert body["platforms"]["x_article"]["cover_media_id"] == "cover"


def test_long_marker_conflict_preserves_structured_diagnostics_and_old_envelope():
    upstream = {"error": {
        "message": "context " * 80, "code": "COMMENTS_MARKER_MISMATCH",
        "details": {"missing": [{"platform": "x", "id": "550e8400-e29b-41d4-a716-446655440000"}]},
    }}
    body = json.dumps(upstream)
    error = APIError(409, body)
    data = error.to_dict()
    assert data["code"] == "api_error" and data["status"] == 409
    assert data["message"] == "API returned 409: " + body[:200]
    assert data["upstream"] == upstream
    assert error.user_message == "API error (HTTP 409)"
    assert "missing" not in error.user_message


@pytest.mark.parametrize("status,upstream", [
    (400, {"error": {"code": "COMMENTS_MARKER_MALFORMED", "details": {"subcode": "mid_mention"}}}),
    (422, {"detail": [{"loc": ["body", "platforms", "x"], "type": "value_error", "msg": "invalid"}]}),
])
def test_marker_subcode_and_validation_details_are_preserved(status, upstream):
    assert APIError(status, json.dumps(upstream)).to_dict()["upstream"] == upstream


def test_diagnostics_redact_secret_fields_and_bound_size():
    upstream = {"message": "context " * 40, "api_key": "secret", "details": {
        "Authorization": "Bearer other-secret", "input": "private post",
        "message": "Bearer abc123 tf_exampletoken https://example.invalid/?token=secret",
    }}
    safe = APIError(422, json.dumps(upstream)).to_dict()["upstream"]
    encoded = json.dumps(safe)
    assert "other-secret" not in encoded and "abc123" not in encoded
    assert "private post" not in encoded and "tf_exampletoken" not in encoded
    assert "token=secret" not in encoded
    error = APIError(422, json.dumps({"details": ["x" * 5000] * 200})).to_dict()
    assert error["upstream_truncated"]
    assert len(json.dumps(error.get("upstream"))) <= 16384


@pytest.mark.parametrize("body", ["not JSON", "<html>bad gateway</html>", '"plain scalar"'])
def test_non_json_error_fallback_remains_compatible(body):
    error = APIError(502, body)
    assert error.to_dict() == {"code": "api_error", "message": "API returned 502: " + body,
                               "status": 502}
