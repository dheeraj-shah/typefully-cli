"""Only synthetic API fixtures and an in-memory HTTP transport; no real account traffic."""

import json
import stat
from unittest.mock import MagicMock

import httpx
import pytest
from click.testing import CliRunner

from typefully_cli import profile_sharing as sharing
from typefully_cli import telemetry
from typefully_cli.cli import cli
from typefully_cli.config import Config

REAL_CLIENT = httpx.Client
REAL_INTERACTIVE = sharing._interactive


def account(platform, username="synthetic_test"):
    urls = {"x": "https://x.com/", "linkedin": "https://www.linkedin.com/in/",
            "bluesky": "https://bsky.app/profile/", "threads": "https://www.threads.net/@",
            "mastodon": "https://social.example.org/@", "substack": "https://substack.com/@"}
    return {"platform": platform, "username": username, "profile_url": urls[platform] + username,
            "name": "PRIVATE_DISPLAY", "profile_image_url": "https://private.example.org/avatar",
            "email": "PRIVATE_EMAIL", "api_key": "PRIVATE_KEY", "followers_count": 123,
            "server": "PRIVATE_INSTANCE", "access_token": "PRIVATE_TOKEN"}


def detail(identifier, platforms=None):
    return {"id": identifier, "name": "PRIVATE_NAME", "username": "PRIVATE_ACCOUNT",
            "team": {"name": "PRIVATE_TEAM"}, "publishing_quota": {"used": 5},
            "platforms": {**dict.fromkeys(sharing.PLATFORMS), **(platforms or {})}}


@pytest.fixture
def world(monkeypatch, tmp_path):
    calls, factories = [], []
    data = {"ids": [1, 2], "details": {1: detail(1, {p: account(p) for p in sharing.PLATFORMS}),
                                       2: detail(2, {"x": account("x", "synthetic_team")})},
            "clock": 1800000000, "api_status": 200, "register_status": 201,
            "sync_status": 201, "withdraw_status": 204,
            "count_override": None, "callback": None}

    def handler(request):
        calls.append(request)
        if data["callback"]:
            data["callback"](request)
        if request.url.host == "api.typefully.com":
            assert request.method == "GET"
            assert request.headers["Authorization"] == "Bearer synthetic-key"
            if data["api_status"] != 200:
                return httpx.Response(data["api_status"], text="PRIVATE_BACKEND_ERROR")
            if request.url.path == "/v2/social-sets":
                assert request.url.params["limit"] == "50"
                offset = int(request.url.params.get("offset", "0"))
                rows = [{"id": i, "team": {"id": "PRIVATE_TEAM"} if i == 2 else None,
                         "username": "PRIVATE_ACCOUNT", "name": "PRIVATE_NAME"}
                        for i in data["ids"][offset:offset + 50]]
                return httpx.Response(200, json={"results": rows,
                    "count": data["count_override"] if data["count_override"] is not None else len(data["ids"]),
                    "next": "https://attacker.invalid/steal?token=PRIVATE_KEY"})
            identifier = int(request.url.path.rstrip("/").rsplit("/", 1)[1])
            assert request.url.path == f"/v2/social-sets/{identifier}/"
            return httpx.Response(200, json=data["details"][identifier])
        assert request.url.host == "profiles.invalid", "No returned URL or other host may be fetched"
        assert request.method == "POST"
        assert not any(key in request.headers for key in ("Authorization", "Cookie", "Proxy-Authorization"))
        assert "PRIVATE_" not in request.content.decode()
        assert "synthetic-key" not in request.content.decode()
        if request.url.path == "/v1/register":
            assert set(json.loads(request.content)) == {"withdrawal_token", "consent_revision", "requested_at"}
            return httpx.Response(data["register_status"])
        return httpx.Response(data["sync_status"] if request.url.path == "/v1/sync" else data["withdraw_status"])

    def factory(**kwargs):
        factories.append(kwargs)
        return REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("TYPEFULLY_API_KEY", "synthetic-key")
    monkeypatch.setattr(sharing, "PROFILE_ENDPOINT", "https://profiles.invalid")
    monkeypatch.setattr(sharing, "_interactive", lambda: True)
    monkeypatch.setattr(sharing.secrets, "token_hex", lambda count: "a" * 64)
    monkeypatch.setattr(sharing.time, "time", lambda: data["clock"])
    monkeypatch.setattr(sharing.httpx, "Client", factory)
    return data, calls, factories


def invoke(command="share-profiles", text="y\n", options=()):
    return CliRunner().invoke(cli, ["community", command, *options], input=text)


def submitted(calls):
    return [json.loads(c.content) for c in calls if c.url.host == "profiles.invalid" and c.url.path == "/v1/sync"]


@pytest.mark.parametrize("answer", ["n\n", "\n"])
def test_decline_before_auth_or_identity_read_or_local_consent(world, monkeypatch, answer):
    _, calls, _ = world
    resolver = MagicMock(side_effect=AssertionError("Do not resolve credentials before consent"))
    monkeypatch.setattr(sharing, "resolve_api_key", resolver)
    result = invoke(text=answer)
    assert result.exit_code == 0, result.output
    assert calls == []
    assert not sharing._state_path().exists()
    resolver.assert_not_called()


def test_single_consent_collects_every_accessible_platform_including_teams(world):
    _, calls, factories = world
    result = invoke()
    assert result.exit_code == 0, result.output
    for phrase in ["team/client", "later", "24 hours", "indefinitely", "withdraw-profiles", "Dheeraj Shah"]:
        assert phrase in result.output
    assert result.output.count("Enable ongoing sharing") == 1
    assert "a" * 64 not in result.output
    payload = submitted(calls)[0]
    assert set(payload) == {"profiles", "withdrawal_token", "consent_revision", "snapshot_at"}
    assert payload["consent_revision"] == "3"
    assert len(payload["profiles"]) == 7
    assert {p["platform"] for p in payload["profiles"]} == set(sharing.PLATFORMS)
    assert any(p["username"] == "synthetic_team" for p in payload["profiles"])
    assert all(set(p) == {"platform", "username", "profile_url"} for p in payload["profiles"])
    receipt_text = sharing._state_path().read_text()
    assert "synthetic_team" not in receipt_text and "synthetic_test" not in receipt_text
    assert stat.S_IMODE(sharing._state_path().stat().st_mode) == 0o600
    assert all(k["follow_redirects"] is False and k["trust_env"] is False for k in factories)
    assert json.loads(receipt_text)["enabled"] is True


def test_ongoing_sync_is_daily_and_includes_new_accounts_and_removed_profiles(world):
    data, calls, _ = world
    assert invoke().exit_code == 0
    count = len(calls)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count
    data["clock"] += sharing.SYNC_INTERVAL + 1
    data["ids"] = [2, 3]
    data["details"][3] = detail(3, {"linkedin": account("linkedin", "synthetic_new_client")})
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    payloads = submitted(calls)
    assert len(payloads) == 2
    assert {p["username"] for p in payloads[-1]["profiles"]} == {"synthetic_team", "synthetic_new_client"}
    assert payloads[-1]["snapshot_at"] == data["clock"]


def test_pagination_reads_all_sets_without_following_returned_urls(world):
    data, calls, _ = world
    data["ids"] = list(range(1, 52))
    data["details"] = {i: detail(i, {"x": account("x", f"synthetic_{i}")}) for i in data["ids"]}
    assert invoke().exit_code == 0
    assert len(submitted(calls)[0]["profiles"]) == 51
    pages = [c for c in calls if c.url.path == "/v2/social-sets"]
    assert [c.url.params["offset"] for c in pages] == ["0", "50"]
    assert all(c.url.host in {"api.typefully.com", "profiles.invalid"} for c in calls)


@pytest.mark.parametrize("status", [301, 403, 404, 429, 500])
def test_lookup_failures_submit_nothing_and_back_off(world, status):
    data, calls, _ = world
    data["api_status"] = status
    result = invoke()
    assert result.exit_code == 2
    assert "PRIVATE_BACKEND_ERROR" not in result.output
    assert submitted(calls) == []
    count = len(calls)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count
    assert sharing._read_state()["enabled"] is True


@pytest.mark.parametrize("mutation", ["missing", "unknown", "no_identifiers", "id", "private_url", "userinfo"])
def test_incomplete_or_invalid_metadata_never_partially_uploads(world, mutation):
    data, calls, _ = world
    value = data["details"][2]
    if mutation == "missing":
        del value["platforms"]["substack"]
    elif mutation == "unknown":
        value["platforms"]["new_platform"] = account("x")
    elif mutation == "no_identifiers":
        value["platforms"]["substack"] = {"username": None, "profile_url": None}
    elif mutation == "id":
        value["id"] = 7
    else:
        value["platforms"]["mastodon"] = account("mastodon")
        value["platforms"]["mastodon"]["profile_url"] = (
            "https://127.0.0.1/@synthetic" if mutation == "private_url" else "https://user:pass@social.example.org/@synthetic")
    assert invoke().exit_code == 2
    assert submitted(calls) == []


def test_substack_nullable_fields_use_only_available_public_identifier(world):
    data, calls, _ = world
    data["details"][1]["platforms"]["substack"] = {"username": "synthetic_substack", "profile_url": None}
    assert invoke().exit_code == 0
    value = next(p for p in submitted(calls)[0]["profiles"] if p["platform"] == "substack")
    assert value == {"platform": "substack", "username": "synthetic_substack"}


def test_duplicates_are_deduplicated_and_empty_snapshot_clears_removed_accounts(world):
    data, calls, _ = world
    data["details"][2] = detail(2, {"x": account("x")})
    assert invoke().exit_code == 0
    assert len(submitted(calls)[0]["profiles"]) == 6
    data["clock"] += sharing.SYNC_INTERVAL
    data["ids"] = []
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert submitted(calls)[-1]["profiles"] == []


@pytest.mark.parametrize("count", [101, -1, "2", True, 3])
def test_inconsistent_or_overlarge_account_lists_send_nothing(world, count):
    data, calls, _ = world
    data["count_override"] = count
    assert invoke().exit_code == 2
    assert submitted(calls) == []


def test_snapshot_size_bound_is_all_or_none(world, monkeypatch):
    _, calls, _ = world
    monkeypatch.setattr(sharing, "MAX_SNAPSHOT_BYTES", 10)
    assert invoke().exit_code == 2
    assert submitted(calls) == []


def test_total_lookup_budget_sends_nothing(world, monkeypatch):
    _, calls, _ = world
    clock = iter([0, 20])
    monkeypatch.setattr(sharing.time, "monotonic", lambda: next(clock))
    assert invoke().exit_code == 2
    assert len(calls) == 1 and calls[0].url.path == "/v1/register"


@pytest.mark.parametrize("status", [302, 400, 503])
def test_uncertain_submission_keeps_receipt_and_does_not_retry_same_day(world, status):
    data, calls, _ = world
    data["sync_status"] = status
    assert invoke().exit_code == 2
    assert sharing._state_path().exists()
    assert len(submitted(calls)) == 1
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(submitted(calls)) == 1


def test_server_withdrawal_tombstone_disables_future_client_sync(world):
    data, calls, _ = world
    data["sync_status"] = 410
    assert invoke().exit_code == 2
    assert sharing._stop_path().exists()
    data["clock"] += sharing.SYNC_INTERVAL + 1
    count = len(calls)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count


@pytest.mark.parametrize("status", [429, 503, 410])
def test_admission_limits_prevent_identity_lookup_and_retains_withdrawal_capability(world, status):
    data, calls, _ = world
    data["register_status"] = status
    result = invoke()
    assert result.exit_code == 2
    assert len(calls) == 1 and calls[0].url.path == "/v1/register"
    assert sharing._state_path().exists()
    assert sharing._read_state()["last_status"] == "admission_unconfirmed"
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == 1


def test_revocation_during_admission_blocks_all_identity_lookup(world):
    data, calls, _ = world
    data["callback"] = lambda request: sharing._disable_locally() if request.url.path == "/v1/register" else None
    assert invoke().exit_code == 0
    assert len(calls) == 1
    assert sharing._read_state()["enabled"] is False


def test_withdraw_stops_sync_before_delete_and_uses_only_token(world):
    data, calls, _ = world
    assert invoke().exit_code == 0
    calls.clear()

    def check(request):
        if request.url.host == "profiles.invalid":
            assert sharing._stop_path().exists()
            assert sharing._read_state()["enabled"] is False
    data["callback"] = check
    result = invoke("withdraw-profiles", options=["--json", "--debug"])
    assert result.exit_code == 0, result.output
    assert len(calls) == 1 and calls[0].url.path == "/v1/withdraw"
    assert json.loads(calls[0].content) == {"withdrawal_token": "a" * 64}
    assert "a" * 64 not in result.output
    assert not sharing._state_path().exists()
    data["clock"] += 86400
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == 1


def test_failed_delete_keeps_local_revocation_and_receipt_for_retry(world):
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["withdraw_status"] = 503
    assert invoke("withdraw-profiles").exit_code == 2
    assert sharing._read_state()["enabled"] is False
    assert sharing._stop_path().exists()
    data["clock"] += 86400
    count = len(calls)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count
    data["withdraw_status"] = 204
    assert invoke("withdraw-profiles").exit_code == 0


def test_revocation_during_lookup_blocks_submission(world):
    data, calls, _ = world
    data["callback"] = lambda request: sharing._disable_locally() if request.url.path.endswith('/2/') else None
    assert invoke().exit_code == 0
    assert submitted(calls) == []
    assert sharing._stop_path().exists()


def test_concurrent_sync_does_not_duplicate_and_withdraw_can_revoke_while_locked(world):
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["clock"] += 86400
    count = len(calls)
    with sharing._lock():
        sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
        assert len(calls) == count
        result = invoke("withdraw-profiles")
        assert result.exit_code == 2
        assert sharing._stop_path().exists()
    assert invoke("withdraw-profiles").exit_code == 0


@pytest.mark.parametrize("command,options", [("config", {}), ("community", {}), (None, {}),
    ("accounts", {"quiet": True}), ("accounts", {"debug": True})])
def test_ineligible_runs_do_not_lookup_or_upload(world, command, options):
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["clock"] += 86400
    count = len(calls)
    sharing.maybe_sync_profiles(command, api_key="synthetic-key", **options)
    assert len(calls) == count


def test_noninteractive_json_and_absent_consent_never_sync(world, monkeypatch):
    data, calls, _ = world
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert calls == []
    assert invoke().exit_code == 0
    data["clock"] += 86400
    count = len(calls)
    monkeypatch.setattr(sharing, "_interactive", lambda: False)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count
    monkeypatch.setattr(sharing, "_interactive", lambda: True)
    cfg = Config.load()
    cfg.output_format = "json"
    cfg.save()
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count


@pytest.mark.parametrize("options", [["--json"], ["--quiet"], ["--debug"]])
def test_consent_requires_unsuppressed_interactive_disclosure(world, options):
    _, calls, _ = world
    assert invoke(options=options).exit_code == 1
    assert calls == []


def test_account_selector_cannot_imply_narrower_consent(world):
    _, calls, _ = world
    result = invoke(options=["--account", "synthetic_personal"])
    assert result.exit_code == 1
    assert calls == []


def test_noninteractive_consent_never_reads_or_sends(world, monkeypatch):
    _, calls, _ = world
    monkeypatch.setattr(sharing, "_interactive", lambda: False)
    assert invoke().exit_code == 1
    assert calls == []


@pytest.mark.parametrize("variable", telemetry.CI_VARIABLES)
def test_real_interactive_gate_excludes_ci(monkeypatch, variable):
    for stream in (sharing.sys.stdin, sharing.sys.stdout, sharing.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    for name in telemetry.CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    assert REAL_INTERACTIVE()
    monkeypatch.setenv(variable, "1")
    assert not REAL_INTERACTIVE()


def test_real_interactive_gate_excludes_redirected_stream(monkeypatch):
    for name in telemetry.CI_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for stream in (sharing.sys.stdin, sharing.sys.stdout, sharing.sys.stderr):
        monkeypatch.setattr(stream, "isatty", lambda: True)
    monkeypatch.setattr(sharing.sys.stdout, "isatty", lambda: False)
    assert not REAL_INTERACTIVE()


def test_anonymous_optout_is_independent_and_old_manual_commands_are_removed(world, monkeypatch):
    monkeypatch.setenv("TYPEFULLY_TELEMETRY", "0")
    assert invoke().exit_code == 0
    assert invoke("share-handle").exit_code == 2
    assert "community" not in telemetry.COMMAND_CATEGORIES


def test_inactive_draft_and_changed_recipient_fail_closed(world, monkeypatch):
    _, calls, _ = world
    monkeypatch.setattr(sharing, "PROFILE_ENDPOINT", "")
    assert invoke().exit_code == 1
    assert calls == []
    assert invoke("privacy").exit_code == 0
    monkeypatch.setattr(sharing, "PROFILE_ENDPOINT", "https://profiles.invalid")
    assert invoke().exit_code == 0
    count = len(calls)
    monkeypatch.setattr(sharing, "PROFILE_ENDPOINT", "https://other.invalid")
    assert invoke("withdraw-profiles").exit_code == 1
    assert len(calls) == count


def test_status_is_local_and_never_prints_token(world):
    _, calls, _ = world
    assert invoke().exit_code == 0
    count = len(calls)
    result = invoke("status")
    assert result.exit_code == 0
    assert "a" * 64 not in result.output
    assert len(calls) == count


def test_successful_command_hook_runs_once_and_failure_does_not_change_command_exit(world, monkeypatch):
    import importlib
    module = importlib.import_module("typefully_cli.cli")
    monkeypatch.setattr(module, "record_usage", lambda *args, **kwargs: None)
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["clock"] += 86400
    data["sync_status"] = 503
    # Existing accounts output is mocked because it is unrelated to sharing behavior.
    monkeypatch.setattr(module, "_output", lambda *args, **kwargs: None)
    result = CliRunner().invoke(cli, ["accounts", "--text"])
    assert result.exit_code == 0, result.output
    assert len(submitted(calls)) == 2
    assert sharing._read_state()["last_status"] == "submission_unconfirmed"


def test_hook_reuses_this_commands_resolved_key_without_second_password_lookup(world, monkeypatch):
    import importlib
    module = importlib.import_module("typefully_cli.cli")
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["clock"] += 86400
    monkeypatch.setattr(module, "record_usage", lambda *args, **kwargs: None)
    resolver = MagicMock(return_value="synthetic-key")
    monkeypatch.setattr(module, "resolve_api_key", resolver)
    extra_lookup = MagicMock(side_effect=AssertionError("Do not prompt for credentials again"))
    monkeypatch.setattr(sharing, "resolve_api_key", extra_lookup)
    monkeypatch.setattr(module, "_output", lambda *args, **kwargs: None)
    result = CliRunner().invoke(cli, ["accounts", "--text"])
    assert result.exit_code == 0, result.output
    assert len(submitted(calls)) == 2
    resolver.assert_called_once()
    extra_lookup.assert_not_called()


def test_automatic_failure_never_changes_command_exit_or_prints_private_backend_errors(world, monkeypatch):
    data, calls, _ = world
    assert invoke().exit_code == 0
    data["clock"] += 86400
    data["api_status"] = 500
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert sharing._read_state()["last_status"] == "lookup_failed"
    assert len(submitted(calls)) == 1


@pytest.mark.parametrize("value", ["null", "{}", "not json"])
def test_malformed_consent_fails_closed_without_lookup(world, value):
    _, calls, _ = world
    path = sharing._state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert calls == []


def test_old_consent_does_not_authorize_connected_profile_collection(world):
    data, calls, _ = world
    assert invoke().exit_code == 0
    state = sharing._read_state()
    state["consent_revision"] = "1"
    sharing._save_state(state)
    data["clock"] += 86400
    count = len(calls)
    sharing.maybe_sync_profiles("accounts", api_key="synthetic-key")
    assert len(calls) == count
    assert invoke("sync-profiles").exit_code == 1
    assert len(calls) == count
