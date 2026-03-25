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
        # Need to mock auth to even get past that
        with patch("typefully_cli.cli._get_client_and_console"):
            result = runner.invoke(cli, ["thread", "only one post"])
        # Should fail with exit code 1
        assert result.exit_code == 1
