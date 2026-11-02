"""Opt-in and withdrawal are exercised only with a mocked, reserved .invalid recipient."""

import importlib
import json
import stat
from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from typefully_cli import handle_sharing as sharing
from typefully_cli.cli import cli
from typefully_cli import telemetry


@pytest.fixture
def setup(monkeypatch, tmp_path):
    path = tmp_path / "handle-sharing.json"
    monkeypatch.setattr(sharing, "HANDLE_ENDPOINT", "https://handles.invalid")
    monkeypatch.setattr(sharing, "_receipt_path", lambda: path)
    monkeypatch.setattr(sharing, "_interactive", lambda: True)
    monkeypatch.setattr(sharing.secrets, "token_hex", lambda count: "a" * 64)
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    response = client.stream.return_value.__enter__.return_value
    response.status_code = 201
    monkeypatch.setattr(sharing.httpx, "Client", factory)
    upstream = MagicMock()
    monkeypatch.setattr(importlib.import_module("typefully_cli.cli"), "TypefullyClient", upstream)
    yield path, factory, client, response
    upstream.assert_not_called()


def invoke(command="share-handle", text="@synthetic_test\ny\n", options=()):
    return CliRunner().invoke(cli, ["community", command, *options], input=text)


def test_share_requires_entered_handle_and_affirmative_confirmation(setup):
    path, factory, client, _ = setup
    result = invoke()
    assert result.exit_code == 0, result.output
    assert "Dheeraj Shah" in result.output
    assert "90-day expiry" in result.output
    assert "withdraw-handle" in result.output
    assert "self-reported" in result.output
    assert "a" * 64 not in result.output
    receipt = json.loads(path.read_text())
    assert receipt == {"endpoint": "https://handles.invalid", "handle": "synthetic_test",
                       "withdrawal_token": "a" * 64}
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    factory.assert_called_once_with(timeout=5.0, follow_redirects=False, trust_env=False)
    client.headers.clear.assert_called_once()
    client.stream.assert_called_once_with(
        "POST", "https://handles.invalid/v1/share",
        headers={"Content-Type": "application/json", "User-Agent": "typefully-cli"},
        json={"handle": "synthetic_test", "withdrawal_token": "a" * 64, "consent_revision": "1"},
    )


@pytest.mark.parametrize("answer", ["n", ""])
def test_decline_is_the_default_and_leaves_no_receipt_or_request(setup, answer):
    path, factory, _, _ = setup
    result = invoke(text="synthetic_test\n" + answer + "\n")
    assert result.exit_code == 0
    assert not path.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("handle", ["https://x.com/synthetic", "a b", "@", "éxample", "x" * 16])
def test_invalid_input_never_sends(setup, handle):
    path, factory, _, _ = setup
    assert invoke(text=handle + "\ny\n").exit_code == 1
    assert not path.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("options", [["--json"], ["--quiet"], ["--debug"]])
def test_share_rejects_automation_and_suppressed_disclosure(setup, options):
    path, factory, _, _ = setup
    assert invoke(options=options).exit_code == 1
    assert not path.exists()
    factory.assert_not_called()


def test_noninteractive_share_never_prompts_or_sends(setup, monkeypatch):
    path, factory, _, _ = setup
    monkeypatch.setattr(sharing, "_interactive", lambda: False)
    result = invoke()
    assert result.exit_code == 1
    assert "Your own X handle" not in result.output
    assert not path.exists()
    factory.assert_not_called()


def test_draft_has_no_recipient_and_cannot_send(setup, monkeypatch):
    _, factory, _, _ = setup
    monkeypatch.setattr(sharing, "HANDLE_ENDPOINT", "")
    assert invoke().exit_code == 1
    result = invoke("privacy")
    assert result.exit_code == 0
    assert "Not activated" in result.output
    factory.assert_not_called()


@pytest.mark.parametrize("recipient", ["http://handles.invalid", "https://user:pass@handles.invalid",
                                        "https://handles.invalid?query=1", "https://handles.invalid:bad"])
def test_unsafe_recipient_never_sends(setup, monkeypatch, recipient):
    _, factory, _, _ = setup
    monkeypatch.setattr(sharing, "HANDLE_ENDPOINT", recipient)
    assert invoke().exit_code == 1
    factory.assert_not_called()


def test_aborted_input_leaves_no_state_or_network(setup, monkeypatch):
    path, factory, _, _ = setup
    # Click 8.1's test runner returns empty strings forever at EOF; simulate its Abort directly.
    monkeypatch.setattr(sharing.click, "prompt", MagicMock(side_effect=sharing.click.Abort))
    assert invoke().exit_code == 0
    assert not path.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("value", ['null', '{}', 'not json', '{"withdrawal_token":[]}'])
def test_malformed_receipt_does_not_send(setup, value):
    path, factory, _, _ = setup
    path.write_text(value)
    assert invoke("withdraw-handle").exit_code == 1
    assert path.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("failure", [302, 400, 503, "timeout"])
def test_uncertain_share_keeps_withdrawal_capability_and_never_retries(setup, failure):
    path, _, client, response = setup
    if failure == "timeout":
        client.stream.side_effect = httpx.ReadTimeout("private secret error")
    else:
        response.status_code = failure
    result = invoke()
    assert result.exit_code == 2
    assert "handle_sharing_unconfirmed" in result.output
    assert "private secret" not in result.output
    assert path.exists()
    assert client.stream.call_count == 1
    assert invoke().exit_code == 1
    assert client.stream.call_count == 1


def test_withdraw_uses_only_token_then_removes_local_receipt(setup):
    path, factory, client, response = setup
    assert invoke().exit_code == 0
    factory.reset_mock()
    response.status_code = 204
    result = invoke("withdraw-handle", options=["--json", "--debug"])
    assert result.exit_code == 0, result.output
    assert not path.exists()
    assert "a" * 64 not in result.output
    client.stream.assert_called_once_with(
        "POST", "https://handles.invalid/v1/withdraw",
        headers={"Content-Type": "application/json", "User-Agent": "typefully-cli"},
        json={"withdrawal_token": "a" * 64},
    )


def test_failed_withdraw_retains_receipt_for_explicit_retry(setup):
    path, _, _, response = setup
    assert invoke().exit_code == 0
    response.status_code = 503
    assert invoke("withdraw-handle").exit_code == 2
    assert path.exists()


def test_changed_recipient_cannot_receive_an_existing_withdrawal_token(setup, monkeypatch):
    _, factory, _, _ = setup
    assert invoke().exit_code == 0
    factory.reset_mock()
    monkeypatch.setattr(sharing, "HANDLE_ENDPOINT", "https://other.invalid")
    assert invoke("withdraw-handle").exit_code == 1
    factory.assert_not_called()


def test_regular_commands_never_prompt_or_share_and_community_is_not_counted(setup):
    _, factory, _, _ = setup
    assert "community" not in telemetry.COMMAND_CATEGORIES
    for command in [[], ["--help"], ["--version"], ["config", "--help"], ["community", "privacy"]]:
        result = CliRunner().invoke(cli, command)
        assert "Your own X handle" not in result.output
    factory.assert_not_called()


def test_telemetry_optout_is_independent_of_explicit_handle_sharing(setup, monkeypatch):
    monkeypatch.setenv("TYPEFULLY_TELEMETRY", "0")
    assert invoke().exit_code == 0


def test_ci_and_real_nonterminal_are_not_interactive(monkeypatch):
    for stream in (sharing.sys.stdin, sharing.sys.stdout, sharing.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    for key in telemetry.CI_VARIABLES:
        monkeypatch.delenv(key, raising=False)
    assert sharing._interactive()
    monkeypatch.setenv("CI", "1")
    assert not sharing._interactive()
    monkeypatch.delenv("CI")
    monkeypatch.setattr(sharing.sys.stdin, "isatty", lambda: False)
    assert not sharing._interactive()
