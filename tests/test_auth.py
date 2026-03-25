"""Tests for auth resolution chain and secret redaction."""

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
