"""Offline public-contract boundary tests; invalid input must not resolve auth."""

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from typefully_cli.cli import cli
from typefully_cli.client import TypefullyClient
from typefully_cli.exceptions import TypefullyError


UUID = "550e8400-e29b-41d4-a716-446655440000"


@pytest.mark.parametrize(
    "args",
    [
        ["tag-create", ""],
        ["tag-create", "x" * 33],
        ["drafts", "--status", "queued"],
        ["drafts", "--order", "random"],
        ["queue"],
        ["queue", "--start-date", "2026-01-01"],
        ["queue", "--start-date", "20260101", "--end-date", "2026-01-02"],
        ["queue", "--start-date", "2026-01-02", "--end-date", "2026-01-01"],
        ["queue", "--start-date", "2026-01-01", "--end-date", "2026-04-01"],
        ["comments", "list", "1", "--platform", "other"],
        ["comments", "list", "1", "--status", "open"],
        ["comments", "reply", "1", "not-a-uuid", "--text", "Hi"],
        ["comments", "reply", "1", UUID, "--text", ""],
        ["comments", "reply", "1", UUID, "--text", "x" * 10001],
        ["comments", "resolve", "1", "../other-route"],
        ["comments", "update", "1", UUID, "invalid", "--text", "Hi"],
        ["comments", "update", "1", UUID, UUID, "--text", ""],
        ["comments", "delete", "1", "invalid"],
        ["comments", "delete", "1", UUID, "invalid"],
        ["media-status", "not-a-uuid"],
        ["media-update", "not-a-uuid", "--clear-alt-text"],
    ],
)
def test_invalid_commands_fail_before_auth(args):
    with patch("typefully_cli.cli._get_client_and_console") as get_client:
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 1, result.output
    assert not result.stdout
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "selected,text,occurrence,platform",
    [
        ("", "Hi", "0", "x"),
        ("x" * 50001, "Hi", "0", "x"),
        ("anchor", "", "0", "x"),
        ("anchor", "x" * 10001, "0", "x"),
        ("anchor", "Hi", "10001", "x"),
        ("anchor", "Hi", "-1", "x"),
        ("anchor", "Hi", "0", "other"),
    ],
)
def test_comment_create_boundaries(selected, text, occurrence, platform):
    args = [
        "comments",
        "create",
        "1",
        "--selected-text",
        selected,
        "--text",
        text,
        "--post-index",
        "0",
        "--occurrence",
        occurrence,
        "--platform",
        platform,
    ]
    with patch("typefully_cli.cli._get_client_and_console") as get_client:
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "rules",
    [
        {},
        None,
        [None],
        [{"h": 0, "m": 0}],
        [{"h": -1, "m": 0, "days": ["mon"]}],
        [{"h": 24, "m": 0, "days": ["mon"]}],
        [{"h": 1, "m": 60, "days": ["mon"]}],
        [{"h": True, "m": 0, "days": ["mon"]}],
        [{"h": 1.5, "m": 0, "days": ["mon"]}],
        [{"h": 0, "m": 0, "days": "mon"}],
        [{"h": 0, "m": 0, "days": [None]}],
        [{"h": 0, "m": 0, "days": []}],
        [{"h": 0, "m": 0, "days": ["mon"], "extra": 1}],
        [{"h": 0, "m": 0, "days": ["MON"]}],
        [{"h": 0, "m": 0, "days": ["mon", "mon"]}],
        [{"h": 0, "m": 0, "days": ["mon"]}, {"h": 0, "m": 0, "days": ["mon", "tue"]}],
    ],
)
def test_invalid_queue_rules_before_auth(rules):
    with patch("typefully_cli.cli._get_client_and_console") as get_client:
        result = CliRunner().invoke(cli, ["queue-schedule", "set", "--rules", json.dumps(rules)])
    assert result.exit_code == 1
    assert json.loads(result.stderr)["error"]["code"] == "invalid_input"
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "args,method,expected",
    [
        (["tag-create", "x" * 32], "create_tag", (7, "x" * 32)),
        (
            ["comments", "reply", "1", UUID, "--text", "x" * 10000],
            "reply_to_comment_thread",
            (7, "1", UUID, "x" * 10000),
        ),
        (["comments", "resolve", "1", UUID], "resolve_comment_thread", (7, "1", UUID)),
        (
            ["comments", "update", "1", UUID, UUID, "--text", "Hi"],
            "update_comment",
            (7, "1", UUID, UUID, "Hi"),
        ),
        (["comments", "delete", "1", UUID], "delete_comment_thread", (7, "1", UUID)),
        (["comments", "delete", "1", UUID, UUID], "delete_comment", (7, "1", UUID, UUID)),
        (["queue-schedule", "set", "--rules", "[]"], "set_queue_schedule", (7, [])),
    ],
)
def test_valid_boundary_inputs_preserve_transport(args, method, expected):
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 7
    getattr(client, method).return_value = {}
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    getattr(client, method).assert_called_once_with(*expected)


def test_invalid_automatic_tag_creation_does_not_send_request():
    with TypefullyClient(api_key="offline") as client:
        client._request = MagicMock()
        with pytest.raises(TypefullyError):
            client.create_tag(7, "x" * 33)
        with pytest.raises(TypefullyError):
            client.ensure_tags(7, ["Valid", "x" * 33])
        client._request.assert_not_called()


@pytest.mark.parametrize("platform,post_index", [("x", ["--post-index", "0"]), ("x_article", [])])
def test_comment_create_valid_maxima_and_output_option_do_not_collide(platform, post_index):
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 7
    client.create_comment_thread.return_value = {"id": UUID}
    args = [
        "comments",
        "create",
        "1",
        "--selected-text",
        "a" * 50000,
        "--text",
        "c" * 10000,
        "--platform",
        platform,
        "--occurrence",
        "10000",
        *post_index,
    ]
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    body = client.create_comment_thread.call_args.args[2]
    assert body["text"] == "c" * 10000
    assert body["occurrence"] == 10000
    assert ("post_index" in body) == (platform == "x")
    assert json.loads(result.stdout)["ok"] is True


@pytest.mark.parametrize("command", ["create", "reply", "update"])
def test_comment_help_has_unique_body_and_human_options(command):
    result = CliRunner().invoke(cli, ["comments", command, "--help"])
    assert result.exit_code == 0
    assert "--human" in result.output
    assert result.output.count("--text") == 1


def test_valid_queue_dates_preserve_response_envelope():
    data = {"days": [{"date": "2026-11-05", "items": []}]}
    client = MagicMock()
    client.__enter__.return_value = client
    client.resolve_account.return_value = 7
    client.get_queue.return_value = data
    with patch(
        "typefully_cli.cli._get_client_and_console", return_value=(client, MagicMock(), MagicMock())
    ):
        result = CliRunner().invoke(
            cli, ["queue", "--start-date", "2026-11-05", "--end-date", "2026-11-05", "--json"]
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"ok": True, "data": data}
    client.get_queue.assert_called_once_with(7, start_date="2026-11-05", end_date="2026-11-05")
