"""Telemetry is exercised exclusively with a fake HTTP client."""

from unittest.mock import MagicMock

import pytest
import httpx

from click.testing import CliRunner

from typefully_cli import telemetry
from typefully_cli.cli import cli
from typefully_cli.config import Config, config_set

REAL_HTTPX_CLIENT = httpx.Client


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("TYPEFULLY_TELEMETRY", raising=False)
    for key in telemetry.CI_VARIABLES:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(telemetry, "ENDPOINT", "https://collector.invalid/usage")
    for stream in (telemetry.sys.stdin, telemetry.sys.stdout, telemetry.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    monkeypatch.setattr(telemetry.httpx, "Client", factory)
    return tmp_path / "typefully" / "telemetry-notice", factory, client


def test_first_notice_no_send_then_exact_payload(setup, capsys, monkeypatch):
    for stream in (telemetry.sys.stdin, telemetry.sys.stdout, telemetry.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    marker, factory, client = setup
    telemetry.record_usage("draft")
    factory.assert_not_called()
    text = capsys.readouterr().err
    assert "Nothing is sent on this run" in text
    assert "TYPEFULLY_TELEMETRY=0" in text
    assert "network IP" in text
    assert marker.exists()
    assert not (marker.parent / "config.toml").exists()
    telemetry.record_usage("draft")
    factory.assert_called_once_with(timeout=0.2, follow_redirects=False, trust_env=False)
    client.headers.clear.assert_called_once()
    client.stream.assert_called_once_with(
        "POST", "https://collector.invalid/usage",
        headers={"Content-Type": "application/json", "User-Agent": "typefully-cli"},
        json={"version": "0.3.0", "category": "drafts"},
    )


@pytest.mark.parametrize("setting", ["0", "false", "off", "no", "FALSE"])
def test_environment_optout(setup, monkeypatch, setting):
    marker, factory, _ = setup
    monkeypatch.setenv("TYPEFULLY_TELEMETRY", setting)
    telemetry.record_usage("draft")
    assert not marker.exists()
    factory.assert_not_called()


def test_config_optout_cannot_be_overridden_by_env(setup, monkeypatch):
    marker, factory, _ = setup
    cfg = Config.load()
    config_set(cfg, "telemetry_enabled", "false")
    monkeypatch.setenv("TYPEFULLY_TELEMETRY", "1")
    telemetry.record_usage("draft")
    assert Config.load().telemetry_enabled is False
    assert not marker.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("key", telemetry.CI_VARIABLES)
def test_ci_always_skipped_even_with_marker(setup, monkeypatch, key):
    _, factory, _ = setup
    telemetry.record_usage("draft")
    monkeypatch.setenv(key, "true")
    telemetry.record_usage("draft")
    factory.assert_not_called()


@pytest.mark.parametrize("stream", ["stdin", "stdout", "stderr"])
def test_noninteractive_always_skipped(setup, monkeypatch, stream):
    _, factory, _ = setup
    telemetry.record_usage("draft")
    monkeypatch.setattr(getattr(telemetry.sys, stream), "isatty", lambda: False)
    telemetry.record_usage("draft")
    factory.assert_not_called()


@pytest.mark.parametrize("command", [None, "config", "completions", "secret text", "help"])
def test_unknown_and_administrative_commands_excluded(setup, command):
    marker, factory, _ = setup
    telemetry.record_usage(command)
    assert not marker.exists()
    factory.assert_not_called()


@pytest.mark.parametrize("endpoint", ["", "http://collector.invalid", "https://u:p@collector.invalid", "https://collector.invalid?q=secret"])
def test_invalid_or_unapproved_endpoint_is_dormant(setup, monkeypatch, endpoint):
    marker, factory, _ = setup
    monkeypatch.setattr(telemetry, "ENDPOINT", endpoint)
    telemetry.record_usage("draft")
    assert not marker.exists()
    factory.assert_not_called()


def test_changed_recipient_requires_new_notice(setup, monkeypatch):
    _, factory, _ = setup
    telemetry.record_usage("draft")
    monkeypatch.setattr(telemetry, "ENDPOINT", "https://other.invalid/usage")
    telemetry.record_usage("draft")
    factory.assert_not_called()


def test_quiet_no_notice_no_send(setup):
    marker, factory, _ = setup
    telemetry.record_usage("draft", quiet=True)
    assert not marker.exists()
    factory.assert_not_called()


def test_failures_do_not_escape(setup):
    _, _, client = setup
    telemetry.record_usage("draft")
    client.stream.side_effect = RuntimeError("secret")
    telemetry.record_usage("draft")


def test_malformed_config_fails_closed(setup):
    marker, factory, _ = setup
    marker.parent.mkdir(parents=True)
    (marker.parent / "config.toml").write_text('[telemetry]\nenabled = "false"\n')
    telemetry.record_usage("draft")
    assert not marker.exists()
    factory.assert_not_called()


def test_config_set_boolean_validation(tmp_path):
    cfg = Config(_path=tmp_path / "config.toml")
    config_set(cfg, "telemetry_enabled", "false")
    assert Config.load(cfg._path).to_dict()["telemetry"] == {"enabled": False}
    with pytest.raises(ValueError):
        config_set(cfg, "telemetry_enabled", "yes")


def test_cli_disabling_config_never_calls_telemetry(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    track = MagicMock()
    monkeypatch.setattr("typefully_cli.cli.record_usage", track)
    result = CliRunner().invoke(cli, ["config", "set", "telemetry_enabled", "false"])
    assert result.exit_code == 0
    track.assert_not_called()
    assert Config.load().telemetry_enabled is False


def test_cli_only_passes_category_source_and_quiet_flag(monkeypatch):
    track = MagicMock()
    monkeypatch.setattr("typefully_cli.cli.record_usage", track)
    monkeypatch.setattr("typefully_cli.cli._get_client_and_console", MagicMock(side_effect=RuntimeError))
    CliRunner().invoke(cli, ["draft", "SECRET POST", "--api-key", "SECRET KEY", "--json"])
    track.assert_called_once_with("draft", quiet=True)


def test_configured_json_mode_excluded(setup):
    marker, factory, _ = setup
    cfg = Config.load()
    config_set(cfg, "output_format", "json")
    telemetry.record_usage("draft")
    assert not marker.exists()
    factory.assert_not_called()


def test_notice_marker_write_failure_never_sends(setup):
    marker, factory, _ = setup
    marker.mkdir(parents=True)
    telemetry.record_usage("draft")
    telemetry.record_usage("draft")
    factory.assert_not_called()


def test_actual_transport_has_only_minimal_request_and_no_redirect(setup, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/steal"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        telemetry.httpx, "Client",
        lambda **kwargs: REAL_HTTPX_CLIENT(transport=transport, **kwargs),
    )
    monkeypatch.setenv("HTTP_PROXY", "http://secret:credential@proxy.invalid")
    monkeypatch.setenv("TYPEFULLY_API_KEY", "SUPER_SECRET")
    telemetry.record_usage("draft")
    telemetry.record_usage("draft")
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://collector.invalid/usage"
    assert request.method == "POST"
    assert request.content == b'{"version":"0.3.0","category":"drafts"}'
    assert dict(request.headers) == {
        "host": "collector.invalid",
        "content-type": "application/json",
        "user-agent": "typefully-cli",
        "content-length": str(len(request.content)),
    }
