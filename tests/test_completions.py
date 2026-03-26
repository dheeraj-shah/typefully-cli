"""Tests for completions install and show commands."""

import json
import os

import pytest
from click.testing import CliRunner
from unittest.mock import patch

from typefully_cli.cli import cli
from typefully_cli.completions import _detect_shell, _rc_already_sourced


@pytest.fixture
def runner():
    return CliRunner()


def _parse_json_line(output: str) -> dict:
    """Parse the first JSON line from mixed stdout/stderr output."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError(f"No JSON found in output: {output!r}")


FAKE_SCRIPT = "# fake completion script\ncomplete -o default typefully\n"


class TestDetectShell:
    def test_detects_zsh(self):
        with patch.dict(os.environ, {"SHELL": "/bin/zsh"}):
            assert _detect_shell() == "zsh"

    def test_detects_bash(self):
        with patch.dict(os.environ, {"SHELL": "/bin/bash"}):
            assert _detect_shell() == "bash"

    def test_detects_fish(self):
        with patch.dict(os.environ, {"SHELL": "/usr/bin/fish"}):
            assert _detect_shell() == "fish"

    def test_raises_on_unknown(self):
        from typefully_cli.exceptions import TypefullyError
        with patch.dict(os.environ, {"SHELL": "/bin/csh"}):
            with pytest.raises(TypefullyError, match="Could not detect shell"):
                _detect_shell()

    def test_raises_on_empty(self):
        from typefully_cli.exceptions import TypefullyError
        with patch.dict(os.environ, {"SHELL": ""}):
            with pytest.raises(TypefullyError, match="Could not detect shell"):
                _detect_shell()


class TestInstall:
    def test_install_writes_script_and_updates_rc(self, runner, tmp_path):
        script_path = tmp_path / ".typefully-complete.zsh"
        rc_path = tmp_path / ".zshrc"
        rc_path.write_text("# existing zshrc\n")

        patched_paths = {
            "bash": tmp_path / ".typefully-complete.bash",
            "zsh": script_path,
            "fish": tmp_path / ".config" / "fish" / "completions" / "typefully.fish",
        }
        patched_rc = {
            "bash": tmp_path / ".bashrc",
            "zsh": rc_path,
        }

        with patch("typefully_cli.completions.SCRIPT_PATHS", patched_paths), \
             patch("typefully_cli.completions.RC_PATHS", patched_rc), \
             patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT), \
             patch("typefully_cli.completions._detect_shell", return_value="zsh"):
            result = runner.invoke(cli, ["completions", "install"])

        assert result.exit_code == 0, result.output + (result.stderr or "")
        data = _parse_json_line(result.output)
        assert data["ok"] is True
        assert data["data"]["shell"] == "zsh"
        assert data["data"]["rc_updated"] is True

        # Script file written
        assert script_path.exists()
        assert script_path.read_text() == FAKE_SCRIPT

        # Source line appended to rc
        rc_content = rc_path.read_text()
        assert f"source {script_path}" in rc_content

    def test_install_idempotent(self, runner, tmp_path):
        script_path = tmp_path / ".typefully-complete.zsh"
        rc_path = tmp_path / ".zshrc"
        # Pre-populate rc with the source line
        rc_path.write_text(f"# existing\nsource {script_path}\n")

        patched_paths = {
            "bash": tmp_path / ".typefully-complete.bash",
            "zsh": script_path,
            "fish": tmp_path / ".config" / "fish" / "completions" / "typefully.fish",
        }
        patched_rc = {
            "bash": tmp_path / ".bashrc",
            "zsh": rc_path,
        }

        with patch("typefully_cli.completions.SCRIPT_PATHS", patched_paths), \
             patch("typefully_cli.completions.RC_PATHS", patched_rc), \
             patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT), \
             patch("typefully_cli.completions._detect_shell", return_value="zsh"):
            result = runner.invoke(cli, ["completions", "install"])

        assert result.exit_code == 0
        data = _parse_json_line(result.output)
        assert data["data"]["rc_updated"] is False

        # Source line not duplicated
        rc_content = rc_path.read_text()
        assert rc_content.count(f"source {script_path}") == 1

    def test_install_with_shell_override(self, runner, tmp_path):
        script_path = tmp_path / ".typefully-complete.bash"
        rc_path = tmp_path / ".bashrc"
        rc_path.write_text("")

        patched_paths = {
            "bash": script_path,
            "zsh": tmp_path / ".typefully-complete.zsh",
            "fish": tmp_path / ".config" / "fish" / "completions" / "typefully.fish",
        }
        patched_rc = {
            "bash": rc_path,
            "zsh": tmp_path / ".zshrc",
        }

        with patch("typefully_cli.completions.SCRIPT_PATHS", patched_paths), \
             patch("typefully_cli.completions.RC_PATHS", patched_rc), \
             patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT):
            result = runner.invoke(cli, ["completions", "install", "--shell", "bash"])

        assert result.exit_code == 0
        data = _parse_json_line(result.output)
        assert data["data"]["shell"] == "bash"
        assert script_path.exists()

    def test_install_fish_no_rc(self, runner, tmp_path):
        fish_path = tmp_path / "fish" / "completions" / "typefully.fish"

        patched_paths = {
            "bash": tmp_path / ".typefully-complete.bash",
            "zsh": tmp_path / ".typefully-complete.zsh",
            "fish": fish_path,
        }
        patched_rc = {
            "bash": tmp_path / ".bashrc",
            "zsh": tmp_path / ".zshrc",
        }

        with patch("typefully_cli.completions.SCRIPT_PATHS", patched_paths), \
             patch("typefully_cli.completions.RC_PATHS", patched_rc), \
             patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT), \
             patch("typefully_cli.completions._detect_shell", return_value="fish"):
            result = runner.invoke(cli, ["completions", "install"])

        assert result.exit_code == 0
        data = _parse_json_line(result.output)
        assert data["data"]["shell"] == "fish"
        # Fish has no rc_path in result
        assert "rc_path" not in data["data"]
        assert fish_path.exists()


class TestShow:
    def test_show_outputs_raw_script(self, runner):
        with patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT), \
             patch("typefully_cli.completions._detect_shell", return_value="zsh"):
            result = runner.invoke(cli, ["completions", "show"])

        assert result.exit_code == 0
        # Raw script present in output
        assert FAKE_SCRIPT.strip() in result.output

    def test_show_with_shell_flag(self, runner):
        with patch("typefully_cli.completions._generate_script", return_value=FAKE_SCRIPT) as mock_gen:
            result = runner.invoke(cli, ["completions", "show", "--shell", "bash"])

        assert result.exit_code == 0
        mock_gen.assert_called_once_with("bash")
        assert FAKE_SCRIPT.strip() in result.output


class TestRcAlreadySourced:
    def test_returns_false_if_no_file(self, tmp_path):
        assert _rc_already_sourced(tmp_path / "nonexistent", "source foo") is False

    def test_returns_true_if_present(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text("source foo\n")
        assert _rc_already_sourced(rc, "source foo") is True

    def test_returns_false_if_absent(self, tmp_path):
        rc = tmp_path / ".zshrc"
        rc.write_text("# nothing here\n")
        assert _rc_already_sourced(rc, "source foo") is False
