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
