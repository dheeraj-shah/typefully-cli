"""Tests for auth resolution chain and secret redaction."""

import os
import stat

import pytest
from typefully_cli.auth import resolve_api_key
from typefully_cli.config import Config, _redact
from typefully_cli.exceptions import AuthError


class TestResolveApiKey:
    def test_cli_flag_wins(self):
        cfg = Config(api_key="config_key")
        assert resolve_api_key("flag_key", "env_key", cfg) == "flag_key"

    def test_env_var_second(self):
        cfg = Config(api_key="config_key")
        assert resolve_api_key(None, "env_key", cfg) == "env_key"

    def test_config_third(self):
        cfg = Config(api_key="config_key")
        assert resolve_api_key(None, None, cfg) == "config_key"

    def test_no_key_raises(self):
        cfg = Config()
        with pytest.raises(AuthError):
            resolve_api_key(None, None, cfg)

    def test_empty_string_skipped(self):
        cfg = Config(api_key="")
        with pytest.raises(AuthError):
            resolve_api_key("", "", cfg)


class TestConfigFilePermissions:
    def test_save_creates_file_owner_only(self, tmp_path):
        cfg = Config(api_key="tf_test_key_12345", _path=tmp_path / "typefully" / "config.toml")
        cfg.save()
        file_mode = stat.S_IMODE(os.stat(cfg._path).st_mode)
        assert file_mode == 0o600, f"Config file should be 0600, got {oct(file_mode)}"

    def test_save_creates_dir_owner_only(self, tmp_path):
        cfg = Config(api_key="tf_test_key_12345", _path=tmp_path / "typefully" / "config.toml")
        cfg.save()
        dir_mode = stat.S_IMODE(os.stat(cfg._path.parent).st_mode)
        assert dir_mode == 0o700, f"Config dir should be 0700, got {oct(dir_mode)}"


class TestRedact:
    def test_normal_key(self):
        assert _redact("tf_abcdefghijklmnop") == "tf_...mnop"

    def test_short_key(self):
        assert _redact("short") == "***"

    def test_empty_key(self):
        assert _redact("") == ""

    def test_exact_boundary(self):
        assert _redact("1234567") == "***"
        assert _redact("12345678") == "123...5678"
