"""Tests for CLI commands using Click CliRunner."""

import json

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from typefully_cli.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_config(tmp_path):
    """Create a temp config with an API key."""
    config_file = tmp_path / "config.toml"
    config_file.write_text('[auth]\napi_key = "tf_test_key_12345"\n\n[defaults]\naccount = "TestBrand"\n')
    return config_file


class TestConfigCommands:
    def test_config_path(self, runner):
        result = runner.invoke(cli, ["config", "path"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "path" in data["data"]

    def test_config_show_redacts_key(self, runner, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('[auth]\napi_key = "tf_secret_key_very_long"\n')
        with patch("typefully_cli.config._config_path", return_value=config_file):
            result = runner.invoke(cli, ["config", "show"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        api_key = data["data"]["auth"]["api_key"]
        assert "secret" not in api_key
        assert api_key.startswith("tf_")
        assert api_key.endswith("long")
        assert "..." in api_key

    def test_config_set_api_key_redacted(self, runner, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        with patch("typefully_cli.config._config_path", return_value=config_file):
            with patch("typefully_cli.cli.Config.load") as mock_load:
                from typefully_cli.config import Config
                mock_load.return_value = Config(_path=config_file)
                result = runner.invoke(cli, ["config", "set", "api_key", "tf_my_secret_12345"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "my_secret" not in data["data"]["value"]

    def test_config_set_default_account(self, runner, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        with patch("typefully_cli.config._config_path", return_value=config_file):
            with patch("typefully_cli.cli.Config.load") as mock_load:
                from typefully_cli.config import Config
                mock_load.return_value = Config(_path=config_file)
                result = runner.invoke(cli, ["config", "set", "default_account", "MyBrand"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["value"] == "MyBrand"


class TestOutputContract:
    """Test that success goes to stdout and errors go to stderr."""

    def test_success_envelope_shape(self, runner):
        result = runner.invoke(cli, ["config", "path"])
        data = json.loads(result.output)
        assert "ok" in data
        assert data["ok"] is True
        assert "data" in data

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert "typefully" in result.output.lower()


class TestBatchDryRun:
    def test_dry_run_outputs_json(self, runner, tmp_path):
        batch_file = tmp_path / "posts.txt"
        batch_file.write_text("tag: test\nFirst post\n---\nSecond post")
        result = runner.invoke(cli, ["batch", str(batch_file), "--dry-run"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["dry_run"] is True
        assert len(data["data"]["entries"]) == 2

    def test_dry_run_with_thread(self, runner, tmp_path):
        batch_file = tmp_path / "posts.txt"
        batch_file.write_text("Post 1\n===\nPost 2")
        result = runner.invoke(cli, ["batch", str(batch_file), "--dry-run"])
        data = json.loads(result.output)
        entries = data["data"]["entries"]
        assert len(entries) == 1
        assert entries[0]["type"] == "thread"
        assert entries[0]["post_count"] == 2

    def test_dry_run_text_mode(self, runner, tmp_path):
        batch_file = tmp_path / "posts.txt"
        batch_file.write_text("A post")
        result = runner.invoke(cli, ["batch", str(batch_file), "--dry-run", "--text"])
        assert result.exit_code == 0
        # Text mode should not be JSON
        assert '"ok"' not in result.output


class TestThreadValidation:
    def test_thread_requires_two_posts(self, runner):
        """Thread with less than 2 posts should fail."""
        with patch("typefully_cli.cli._get_client_and_console"):
            result = runner.invoke(cli, ["thread", "only one post"])
        assert result.exit_code == 1


class TestDateValidation:
    """Test --since/--until date validation on the recent command."""

    def test_valid_date_accepted(self, runner):
        with patch("typefully_cli.cli._get_client_and_console") as mock_gcc:
            from unittest.mock import MagicMock
            from typefully_cli.config import Config
            from typefully_cli.console import Console

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.resolve_account.return_value = 123
            mock_client.list_recent.return_value = []
            mock_gcc.return_value = (mock_client, Console(quiet=True), Config(default_account="test"))
            result = runner.invoke(cli, ["recent", "--since", "2024-01-01"])
        assert result.exit_code == 0

    def test_invalid_since_rejected(self, runner):
        result = runner.invoke(cli, ["recent", "--since", "not-a-date"])
        assert result.exit_code == 1
        # Should produce structured JSON error, not raw Click text
        assert '"invalid_input"' in result.output

    def test_invalid_until_rejected(self, runner):
        result = runner.invoke(cli, ["recent", "--until", "nope"])
        assert result.exit_code == 1

    def test_since_after_until_rejected(self, runner):
        result = runner.invoke(cli, ["recent", "--since", "2025-12-01", "--until", "2025-01-01"])
        assert result.exit_code == 1
        assert '"invalid_input"' in result.output

    def test_empty_dates_accepted(self, runner):
        with patch("typefully_cli.cli._get_client_and_console") as mock_gcc:
            from unittest.mock import MagicMock
            from typefully_cli.config import Config
            from typefully_cli.console import Console

            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.resolve_account.return_value = 123
            mock_client.list_recent.return_value = []
            mock_gcc.return_value = (mock_client, Console(quiet=True), Config(default_account="test"))
            result = runner.invoke(cli, ["recent"])
        assert result.exit_code == 0


class TestLimitValidation:
    """Test that --limit is capped at 50."""

    def test_drafts_limit_over_50_rejected(self, runner):
        result = runner.invoke(cli, ["drafts", "-n", "100"])
        assert result.exit_code == 1
        assert '"invalid_input"' in result.output

    def test_tags_limit_over_50_rejected(self, runner):
        result = runner.invoke(cli, ["tags", "-n", "100"])
        assert result.exit_code == 1

    def test_recent_limit_over_50_rejected(self, runner):
        result = runner.invoke(cli, ["recent", "-n", "100"])
        assert result.exit_code == 1

    def test_drafts_limit_zero_rejected(self, runner):
        result = runner.invoke(cli, ["drafts", "-n", "0"])
        assert result.exit_code == 1


class TestCleanErrorPayloads:
    """Test that partial-failure stdout errors don't contain raw API bodies."""

    def test_delete_partial_errors_are_clean(self, runner):
        from unittest.mock import MagicMock
        from typefully_cli.config import Config
        from typefully_cli.console import Console
        from typefully_cli.exceptions import APIError

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.resolve_account.return_value = 123
        mock_client.rate_delay.return_value = None
        mock_client.delete_draft.side_effect = [None, APIError(404, '{"detail":"Not found","code":"not_found"}')]

        with patch("typefully_cli.cli._get_client_and_console", return_value=(
            mock_client, Console(quiet=True), Config(default_account="test")
        )):
            result = runner.invoke(cli, ["delete", "id1", "id2"])

        assert result.exit_code == 3
        jsons = []
        for line in result.output.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    jsons.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        success = [j for j in jsons if j.get("ok") is True]
        assert len(success) == 1
        errors_list = success[0]["data"]["errors"]
        assert len(errors_list) == 1
        # Must NOT contain raw API body
        assert "Not found" not in errors_list[0]["message"]
        assert "detail" not in errors_list[0]["message"]
        # Should contain clean message
        assert "HTTP 404" in errors_list[0]["message"]


class TestConfigInit:
    def _make_mock_gcc(self, tmp_path, api_key_in_config=None):
        """Return a (mock_client, console, config) tuple for patching _get_client_and_console."""
        from unittest.mock import MagicMock
        from typefully_cli.config import Config
        from typefully_cli.console import Console

        config_file = tmp_path / "config.toml"
        if api_key_in_config:
            config_file.write_text(f'[auth]\napi_key = "{api_key_in_config}"\n')
        else:
            config_file.write_text("")

        cfg = Config(_path=config_file)
        if api_key_in_config:
            cfg.api_key = api_key_in_config

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.me.return_value = {"name": "TestUser"}

        console = Console(quiet=True)
        return mock_client, console, cfg, config_file

    def test_successful_init(self, runner, tmp_path):
        """Fresh config: prompts for key, validates, saves, outputs success JSON."""
        from unittest.mock import MagicMock, patch
        from typefully_cli.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        cfg = Config(_path=config_file)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.me.return_value = {"name": "TestUser"}

        with patch("typefully_cli.cli.Config.load", return_value=cfg):
            with patch("typefully_cli.cli.TypefullyClient", return_value=mock_client):
                result = runner.invoke(
                    cli,
                    ["config", "init"],
                    input="tf_testkey_12345\n\n",
                )

        assert result.exit_code == 0
        data = json.loads(result.output.strip().splitlines()[-1])
        assert data["ok"] is True
        assert data["data"]["message"] == "Config saved"

    def test_invalid_key_exits_1(self, runner, tmp_path):
        """Invalid API key: client.me() raises, exits 1."""
        from unittest.mock import MagicMock, patch
        from typefully_cli.config import Config
        from typefully_cli.exceptions import TypefullyError

        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        cfg = Config(_path=config_file)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.me.side_effect = TypefullyError("Unauthorized", code="auth_failed")

        with patch("typefully_cli.cli.Config.load", return_value=cfg):
            with patch("typefully_cli.cli.TypefullyClient", return_value=mock_client):
                result = runner.invoke(
                    cli,
                    ["config", "init"],
                    input="tf_badkey\n",
                )

        assert result.exit_code == 1

    def test_existing_config_overwrite_declined(self, runner, tmp_path):
        """Config already exists and user declines overwrite: aborts cleanly."""
        from unittest.mock import patch
        from typefully_cli.config import Config

        config_file = tmp_path / "config.toml"
        config_file.write_text('[auth]\napi_key = "tf_existing_key"\n')
        cfg = Config(_path=config_file)
        cfg.api_key = "tf_existing_key"

        with patch("typefully_cli.cli.Config.load", return_value=cfg):
            result = runner.invoke(
                cli,
                ["config", "init"],
                input="n\n",
            )

        assert result.exit_code == 0
        assert "Aborted" in result.output


class TestOpenDraft:
    def _mock_gcc(self, draft_data):
        """Return a (mock_client, console, config) patchable triple."""
        from unittest.mock import MagicMock
        from typefully_cli.config import Config
        from typefully_cli.console import Console

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.resolve_account.return_value = 123
        mock_client.get_draft.return_value = draft_data

        return mock_client, Console(quiet=True), Config(default_account="test")

    def test_successful_open(self, runner):
        """Happy path: launch returns 0, opened=True in JSON."""
        draft = {"id": "d1", "private_url": "https://typefully.com/drafts/d1"}
        mock_client, console, config = self._mock_gcc(draft)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            with patch("typefully_cli.cli.click.launch", return_value=0) as mock_launch:
                result = runner.invoke(cli, ["open", "d1"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["opened"] is True
        assert data["data"]["url"] == "https://typefully.com/drafts/d1"
        mock_launch.assert_called_once_with("https://typefully.com/drafts/d1")

    def test_no_url_exits_2(self, runner):
        """Draft has no URL: exits 2 with error JSON."""
        draft = {"id": "d1"}
        mock_client, console, config = self._mock_gcc(draft)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            result = runner.invoke(cli, ["open", "d1"])

        assert result.exit_code == 2

    def test_launch_fails_prints_url(self, runner):
        """launch() returns non-zero: opened=False, URL still included."""
        draft = {"id": "d1", "share_url": "https://typefully.com/share/d1"}
        mock_client, console, config = self._mock_gcc(draft)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            with patch("typefully_cli.cli.click.launch", return_value=1):
                result = runner.invoke(cli, ["open", "d1"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["data"]["opened"] is False
        assert data["data"]["url"] == "https://typefully.com/share/d1"

    def test_share_url_fallback(self, runner):
        """No private_url but share_url present: uses share_url fallback."""
        draft = {"id": "d2", "private_url": "", "share_url": "https://typefully.com/share/d2"}
        mock_client, console, config = self._mock_gcc(draft)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            with patch("typefully_cli.cli.click.launch", return_value=0):
                result = runner.invoke(cli, ["open", "d2"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["url"] == "https://typefully.com/share/d2"


class TestRecentCsv:
    def _mock_gcc(self, posts):
        from unittest.mock import MagicMock
        from typefully_cli.config import Config
        from typefully_cli.console import Console

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.resolve_account.return_value = 123
        mock_client.list_recent.return_value = posts

        return mock_client, Console(quiet=True), Config(default_account="test")

    def test_csv_headers_and_rows(self, runner):
        """CSV output contains correct header row and one data row."""
        posts = [
            {
                "id": "p1",
                "published_at": "2024-06-01T12:00:00Z",
                "platforms": {
                    "x": {"posts": [{"text": "Hello world tweet"}]}
                },
                "x_published_url": "https://x.com/user/status/1",
            }
        ]
        mock_client, console, config = self._mock_gcc(posts)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            result = runner.invoke(cli, ["recent", "--format", "csv"])

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert lines[0] == "id,published_at,text,x_url"
        assert len(lines) == 2
        assert "p1" in lines[1]
        assert "Hello world tweet" in lines[1]
        assert "https://x.com/user/status/1" in lines[1]

    def test_csv_empty_posts_headers_only(self, runner):
        """Empty posts list produces only the header row."""
        mock_client, console, config = self._mock_gcc([])

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            result = runner.invoke(cli, ["recent", "--format", "csv"])

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        assert lines == ["id,published_at,text,x_url"]

    def test_csv_text_truncated_to_280(self, runner):
        """Text longer than 280 chars is truncated in CSV output."""
        long_text = "x" * 400
        posts = [
            {
                "id": "p2",
                "published_at": "2024-06-01T12:00:00Z",
                "platforms": {"x": {"posts": [{"text": long_text}]}},
                "x_published_url": "",
            }
        ]
        mock_client, console, config = self._mock_gcc(posts)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            result = runner.invoke(cli, ["recent", "--format", "csv"])

        assert result.exit_code == 0
        lines = result.output.strip().splitlines()
        # The text field in the CSV row should be max 280 chars
        import csv as csv_mod
        row = list(csv_mod.reader([lines[1]]))[0]
        assert len(row[2]) <= 280

    def test_csv_falls_back_to_preview(self, runner):
        """If platforms.x is missing, falls back to draft preview field."""
        posts = [
            {
                "id": "p3",
                "published_at": "2024-06-02T09:00:00Z",
                "preview": "Preview text here",
                "x_published_url": "",
            }
        ]
        mock_client, console, config = self._mock_gcc(posts)

        with patch("typefully_cli.cli._get_client_and_console", return_value=(mock_client, console, config)):
            result = runner.invoke(cli, ["recent", "--format", "csv"])

        assert result.exit_code == 0
        assert "Preview text here" in result.output


class TestDeletePartialFailure:
    """Test the three-branch contract for delete."""

    def _mock_client(self, delete_side_effects):
        """Create mock client where delete_draft has per-call side effects."""
        from unittest.mock import MagicMock
        from typefully_cli.client import TypefullyClient
        from typefully_cli.config import Config
        from typefully_cli.console import Console
        from typefully_cli.exceptions import APIError

        mock_client = MagicMock(spec=TypefullyClient)
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.resolve_account.return_value = 123
        mock_client.rate_delay.return_value = None

        effects = []
        for effect in delete_side_effects:
            if effect == "ok":
                effects.append(None)
            else:
                effects.append(APIError(404, "Not found"))
        mock_client.delete_draft.side_effect = effects

        mock_console = Console(quiet=True)
        mock_config = Config(default_account="test")
        return mock_client, mock_console, mock_config

    def _parse_json_lines(self, output):
        """Parse all JSON objects from mixed output (stdout + stderr merged by CliRunner)."""
        results = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results

    def test_all_succeed_exit_0(self, runner):
        client, console, config = self._mock_client(["ok", "ok"])
        with patch("typefully_cli.cli._get_client_and_console", return_value=(client, console, config)):
            result = runner.invoke(cli, ["delete", "id1", "id2"])
        assert result.exit_code == 0
        jsons = self._parse_json_lines(result.output)
        success = [j for j in jsons if j.get("ok") is True]
        assert len(success) == 1
        assert len(success[0]["data"]["deleted"]) == 2

    def test_all_fail_exit_2(self, runner):
        client, console, config = self._mock_client(["fail", "fail"])
        with patch("typefully_cli.cli._get_client_and_console", return_value=(client, console, config)):
            result = runner.invoke(cli, ["delete", "id1", "id2"])
        assert result.exit_code == 2
        jsons = self._parse_json_lines(result.output)
        # Only error JSON, no success JSON
        errors = [j for j in jsons if j.get("ok") is False]
        success = [j for j in jsons if j.get("ok") is True]
        assert len(errors) == 1
        assert errors[0]["error"]["code"] == "all_failed"
        assert len(success) == 0

    def test_partial_fail_exit_3(self, runner):
        client, console, config = self._mock_client(["ok", "fail"])
        with patch("typefully_cli.cli._get_client_and_console", return_value=(client, console, config)):
            result = runner.invoke(cli, ["delete", "id1", "id2"])
        assert result.exit_code == 3
        jsons = self._parse_json_lines(result.output)
        # Both success data and error envelope
        success = [j for j in jsons if j.get("ok") is True]
        errors = [j for j in jsons if j.get("ok") is False]
        assert len(success) == 1
        assert len(success[0]["data"]["deleted"]) == 1
        assert len(errors) == 1
        assert errors[0]["error"]["code"] == "partial_failure"
        assert errors[0]["error"]["status"] == 3


# ---------------------------------------------------------------------------
# Helper: patch TypefullyClient so __enter__ returns the mock client itself
# ---------------------------------------------------------------------------

def _patch_client(mock_config):
    """Return a (config_patch, client_patch_cls) context-manager pair.

    Usage::

        with _config_patch(mock_config):
            with _client_patch() as MockClient:
                client = MockClient.return_value
                client.resolve_account.return_value = 1
                ...
    """


def _make_client_mock(MockClient):
    """Wire up MockClient so that ``with TypefullyClient(...) as c`` works and
    methods are accessible on the same object returned by the constructor."""
    from unittest.mock import MagicMock
    inst = MockClient.return_value
    inst.__enter__ = MagicMock(return_value=inst)
    inst.__exit__ = MagicMock(return_value=False)
    inst.get_social_sets.return_value = [{"id": 1, "username": "TestBrand"}]
    inst.resolve_account.return_value = 1
    return inst


class TestAnalytics:
    def test_analytics_json(self, runner, mock_config):
        mock_data = {
            "results": [
                {"id": 1, "text": "Hello", "impressions": 100, "likes": 10,
                 "published_at": "2026-01-01"}
            ]
        }
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.list_analytics.return_value = mock_data
                result = runner.invoke(cli, ["analytics", "--start-date", "2026-01-01"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_analytics_invalid_date(self, runner, mock_config):
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                _make_client_mock(MockClient)
                result = runner.invoke(cli, ["analytics", "--start-date", "bad-date"])
        assert result.exit_code == 1


class TestQueue:
    def test_queue_json(self, runner, mock_config):
        mock_data = {
            "slots": [
                {"time": "2026-01-01T09:00:00",
                 "draft": {"id": 1, "preview": "Hello"}}
            ]
        }
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.get_queue.return_value = mock_data
                result = runner.invoke(cli, ["queue"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestQueueSchedule:
    def test_get_schedule(self, runner, mock_config):
        mock_data = {"rules": [{"h": 9, "m": 30, "days": ["mon", "wed"]}]}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.get_queue_schedule.return_value = mock_data
                result = runner.invoke(cli, ["queue-schedule", "get"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True

    def test_set_schedule(self, runner, mock_config):
        rules_json = '[{"h":9,"m":30,"days":["mon","wed"]}]'
        mock_data = {"rules": [{"h": 9, "m": 30, "days": ["mon", "wed"]}]}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.set_queue_schedule.return_value = mock_data
                result = runner.invoke(cli, ["queue-schedule", "set", "--rules", rules_json])
        assert result.exit_code == 0

    def test_set_schedule_missing_rules(self, runner, mock_config):
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                _make_client_mock(MockClient)
                result = runner.invoke(cli, ["queue-schedule", "set"])
        assert result.exit_code == 1

    def test_set_schedule_invalid_json(self, runner, mock_config):
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                _make_client_mock(MockClient)
                result = runner.invoke(cli, ["queue-schedule", "set", "--rules", "not json"])
        assert result.exit_code == 1


class TestLinkedInResolve:
    def test_resolve_json(self, runner, mock_config):
        mock_data = {
            "name": "Typefully",
            "mention_text": "@[Typefully](urn:li:organization:86779668)",
        }
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.resolve_linkedin_org.return_value = mock_data
                result = runner.invoke(
                    cli,
                    ["linkedin-resolve", "https://linkedin.com/company/typefully"],
                )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestPublish:
    def test_publish_json(self, runner, mock_config):
        mock_data = {"id": 123, "status": "published"}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.update_draft.return_value = mock_data
                result = runner.invoke(cli, ["publish", "123"])
        assert result.exit_code == 0
        # Verify it called update_draft with publish_at=now
        client.update_draft.assert_called_once_with(1, "123", {"publish_at": "now"})


class TestScheduleCmd:
    def test_schedule_default_next(self, runner, mock_config):
        mock_data = {"id": 123, "status": "scheduled"}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.update_draft.return_value = mock_data
                result = runner.invoke(cli, ["schedule", "123"])
        assert result.exit_code == 0
        client.update_draft.assert_called_once_with(
            1, "123", {"publish_at": "next-free-slot"}
        )

    def test_schedule_specific_time(self, runner, mock_config):
        mock_data = {"id": 123, "status": "scheduled"}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.update_draft.return_value = mock_data
                result = runner.invoke(
                    cli,
                    ["schedule", "123", "--time", "2026-04-01T10:00:00Z"],
                )
        assert result.exit_code == 0
        client.update_draft.assert_called_once_with(
            1, "123", {"publish_at": "2026-04-01T10:00:00Z"}
        )


class TestMediaStatus:
    def test_media_status_json(self, runner, mock_config):
        mock_data = {
            "id": "abc", "status": "ready",
            "url": "https://example.com/media.jpg",
        }
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.get_media.return_value = mock_data
                result = runner.invoke(cli, ["media-status", "abc"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True


class TestDraftFileInput:
    def test_draft_from_file(self, runner, mock_config, tmp_path):
        post_file = tmp_path / "post.txt"
        post_file.write_text("Hello from file")
        mock_data = {"id": 1, "status": "draft"}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.ensure_tags.return_value = []
                client.create_draft.return_value = mock_data
                result = runner.invoke(cli, ["draft", "--file", str(post_file)])
        assert result.exit_code == 0

    def test_draft_no_text_no_file(self, runner, mock_config):
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                _make_client_mock(MockClient)
                result = runner.invoke(cli, ["draft"])
        assert result.exit_code == 1


class TestAllPlatformsFlag:
    def test_draft_all_platforms(self, runner, mock_config):
        mock_data = {"id": 1, "status": "draft"}
        ss_data = {
            "id": 1,
            "platforms": {"x": {}, "linkedin": {}, "threads": {}},
        }
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.get_social_set.return_value = ss_data
                client.ensure_tags.return_value = []
                client.create_draft.return_value = mock_data
                result = runner.invoke(cli, ["draft", "Hello world", "--all"])
        assert result.exit_code == 0
        # Verify create_draft was called with linkedin and threads enabled
        call_args = client.create_draft.call_args
        payload = call_args[0][1]
        assert "linkedin" in payload["platforms"]
        assert "threads" in payload["platforms"]


class TestAppendFlag:
    def test_update_append(self, runner, mock_config):
        existing_draft = {
            "id": 123,
            "platforms": {
                "x": {"enabled": True, "posts": [{"text": "Original post"}]}
            },
        }
        updated_data = {"id": 123, "status": "draft"}
        with patch("typefully_cli.config._config_path", return_value=mock_config):
            with patch("typefully_cli.cli.TypefullyClient") as MockClient:
                client = _make_client_mock(MockClient)
                client.get_draft.return_value = existing_draft
                client.update_draft.return_value = updated_data
                result = runner.invoke(
                    cli, ["update", "123", "New post", "--append"]
                )
        assert result.exit_code == 0
        call_args = client.update_draft.call_args
        payload = call_args[0][2]
        posts = payload["platforms"]["x"]["posts"]
        assert len(posts) == 2
        assert posts[0]["text"] == "Original post"
        assert posts[1]["text"] == "New post"
