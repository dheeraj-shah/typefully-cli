"""Config file management: ~/.config/typefully/config.toml"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]


def _toml_escape(value: str) -> str:
    """Escape a string for TOML basic string (double-quoted)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _config_path() -> Path:
    """Return the config file path. Respects XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(base) / "typefully" / "config.toml"


@dataclass
class Config:
    api_key: str = ""
    onepassword_item: str = ""
    default_account: str = ""
    _path: Path = field(default_factory=_config_path)

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        p = path or _config_path()
        cfg = cls(_path=p)
        if not p.exists():
            return cfg
        with open(p, "rb") as f:
            data = tomllib.load(f)
        auth = data.get("auth", {})
        cfg.api_key = auth.get("api_key", "")
        cfg.onepassword_item = auth.get("onepassword_item", "")
        defaults = data.get("defaults", {})
        cfg.default_account = defaults.get("account", "")
        return cfg

    def save(self) -> None:
        """Write config back to TOML. Minimal hand-written TOML (no dependency)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self._path.parent, 0o700)
        lines: list[str] = []
        lines.append("[auth]")
        if self.api_key:
            lines.append(f'api_key = "{_toml_escape(self.api_key)}"')
        if self.onepassword_item:
            lines.append(f'onepassword_item = "{_toml_escape(self.onepassword_item)}"')
        lines.append("")
        lines.append("[defaults]")
        if self.default_account:
            lines.append(f'account = "{_toml_escape(self.default_account)}"')
        lines.append("")
        self._path.write_text("\n".join(lines))
        os.chmod(self._path, 0o600)

    def to_dict(self, *, redact: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "auth": {
                "api_key": _redact(self.api_key) if redact else self.api_key,
            },
            "defaults": {},
        }
        if self.onepassword_item:
            d["auth"]["onepassword_item"] = self.onepassword_item
        if self.default_account:
            d["defaults"]["account"] = self.default_account
        return d


# --- Config set/show helpers ---

_VALID_KEYS = {"api_key", "default_account", "onepassword_item"}


def config_set(cfg: Config, key: str, value: str) -> dict:
    """Set a config key. Returns the result dict (api_key redacted)."""
    if key not in _VALID_KEYS:
        raise ValueError(f"Unknown config key: {key}. Valid: {', '.join(sorted(_VALID_KEYS))}")
    if key == "api_key":
        cfg.api_key = value
    elif key == "default_account":
        cfg.default_account = value
    elif key == "onepassword_item":
        cfg.onepassword_item = value
    cfg.save()
    display_value = _redact(value) if key == "api_key" else value
    return {"key": key, "value": display_value}


def _redact(key: str) -> str:
    """Redact an API key: show first 3 and last 4 chars."""
    if not key:
        return ""
    if len(key) <= 7:
        return "***"
    return f"{key[:3]}...{key[-4:]}"
