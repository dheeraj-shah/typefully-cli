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


@pytest.mark.parametrize("action,options", [
    (action, options)
    for action in ("draft", "update")
    for options in (
        ["--media", "media-id"], ["--paid-partnership"], ["--made-with-ai"],
        ["--hide-link-preview"], ["--community", "123"],
        ["--quote-post-url", "https://x.com/a/status/1"],
        ["--linkedin-first-comment", "Hi"], ["--no-subscribers-only"],
        ["--reply-settings", "null"], ["--share-with-followers"],
        ["--all"], ["--linkedin"],
    )
    if action == "draft" or options[0] not in ("--all", "--linkedin")
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


def test_diagnostics_mark_truncated_keys_and_large_structured_values():
    error = APIError(422, json.dumps({
        "x" * 200: "value", "details": ["item" * 100] * 90,
    })).to_dict()
    assert error["upstream_truncated"]
    assert len(json.dumps(error["upstream"])) <= 16384


def test_error_envelope_redacts_sensitive_fields_at_the_front_too():
    body = json.dumps({
        "api_key": "key-at-front", "input": {"text": "private-at-front"},
        "headers": {"Authorization": "Bearer front-token"},
        "request": {"body": "private-request"},
        "error": {"code": "VALIDATION_ERROR", "message": "Bearer message-token tf_secretkey",
                  "details": {"subcode": "mid_mention"}},
    })
    error = APIError(400, body)
    envelope = json.dumps({"ok": False, "error": error.to_dict()})
    for secret in ("key-at-front", "private-at-front", "front-token",
                   "private-request", "message-token", "tf_secretkey"):
        assert secret not in envelope
    assert error.to_dict()["code"] == "api_error"
    assert error.to_dict()["status"] == 400
    assert error.user_message == "API error (HTTP 400)"
    assert error.to_dict()["upstream"]["error"]["details"]["subcode"] == "mid_mention"


@pytest.mark.parametrize("body,secret", [
    ("Bearer plain-token failed", "plain-token"),
    ("Invalid tf_example-secret in response", "tf_example-secret"),
    ('{"input": "private-incomplete', "private-incomplete"),
])
def test_unparsed_message_preview_redacts_recognized_sensitive_values(body, secret):
    assert secret not in json.dumps(APIError(502, body).to_dict())


@pytest.mark.parametrize("action", ["draft", "update"])
@pytest.mark.parametrize("platform", ["x", "linkedin"])
@pytest.mark.parametrize("field,value", [
    ("--content-markdown", "# Title"), ("--cover-media-id", "null"),
])
def test_article_fields_reject_explicit_post_platform_before_auth(action, platform, field, value):
    args = [action, *(["2"] if action == "update" else []),
            "--platform", platform, field, value, "--tag", "Must not be created"]
    with patch("typefully_cli.cli._get_client_and_console") as auth:
        result = runner().invoke(cli, args)
    assert result.exit_code == 1, result.output
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    auth.assert_not_called()


def test_new_tag_aliases_reuse_slug_even_if_server_canonicalizes_name():
    with client_with_tags([], created={"name": "Canonical", "slug": "opaque"}) as client:
        resolved = client.resolve_tag_slugs(1, ["New Tag", "new tag", "New Tag"])
        assert set(resolved.values()) == {"opaque"}
        client.create_tag.assert_called_once_with(1, "New Tag")


def test_article_validator_preserves_omitted_platform_selection():
    from typefully_cli.validation import validate_article_input

    options = {}
    validate_article_input(None, "# Title", None, options)
    assert options == {}


@pytest.mark.parametrize("value,expected", [
    ("2027-01-01T10:00:00", "2027-01-01T04:30:00Z"),
    ("2027-01-01T10:00:00+02:00", "2027-01-01T10:00:00+02:00"),
    ("2027-01-01T10:00:00Z", "2027-01-01T10:00:00Z"),
    ("next", "next-free-slot"),
])
def test_draft_plan_uses_configured_timezone(value, expected):
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 1
    client.create_draft.return_value = {"id": 2, "status": "planned"}
    cfg = Config(default_account="offline", timezone="Asia/Kolkata")
    with patch("typefully_cli.cli._get_client_and_console",
               return_value=(client, Console(quiet=True), cfg)):
        result = runner().invoke(cli, ["draft", "Hello", "--plan", value, "--json", "--quiet"])
    assert result.exit_code == 0, result.output
    payload = client.create_draft.call_args.args[1]
    assert payload["plan_at"] == expected
    assert "publish_at" not in payload


@pytest.mark.parametrize("append", [True, False])
def test_update_nullable_selected_platform(append):
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 1
    client.get_draft.return_value = {"platforms": {"x": None}}
    client.update_draft.return_value = {"id": 2, "status": "draft"}
    args = ["update", "2", "--platform", "x", "--json", "--quiet"]
    args += ["New post", "--append"] if append else ["--media", "existing-media-id"]
    with patch("typefully_cli.cli._get_client_and_console",
               return_value=(client, Console(quiet=True), Config(default_account="offline"))):
        result = runner().invoke(cli, args)
    if append:
        assert result.exit_code == 0, result.output
        assert client.update_draft.call_args.args[2]["platforms"]["x"]["posts"] == [{"text": "New post"}]
    else:
        assert result.exit_code == 1, result.output
        assert "invalid_input" in result.output
        client.update_draft.assert_not_called()
