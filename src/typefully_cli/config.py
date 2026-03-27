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
    output_format: str = "text"
    default_platforms: str = ""
    timezone: str = ""
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
        cfg.output_format = defaults.get("output_format", "text")
        cfg.default_platforms = defaults.get("platforms", "")
        cfg.timezone = defaults.get("timezone", "")
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
        if self.output_format:
            lines.append(f'output_format = "{_toml_escape(self.output_format)}"')
        if self.default_platforms:
            lines.append(f'platforms = "{_toml_escape(self.default_platforms)}"')
        if self.timezone:
            lines.append(f'timezone = "{_toml_escape(self.timezone)}"')
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
        d["defaults"]["output_format"] = self.output_format
        if self.default_platforms:
            d["defaults"]["platforms"] = self.default_platforms
        if self.timezone:
            d["defaults"]["timezone"] = self.timezone
        return d


# --- Config set/show helpers ---

_VALID_KEYS = {
    "api_key", "default_account", "onepassword_item", "output_format",
    "default_platforms", "timezone",
}

_KNOWN_PLATFORMS = {"x", "linkedin", "threads", "bluesky", "mastodon"}


def _validate_timezone(tz_name: str) -> str:
    """Validate a timezone name. Returns canonical name or raises."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError):
        raise ValueError(
            f"Unknown timezone: '{tz_name}'. "
            f"Use IANA names like 'Asia/Kolkata', 'US/Eastern', 'Europe/London'."
        )
    return tz_name


def _validate_platforms(platforms_str: str) -> str:
    """Validate a comma-separated platforms string. Returns cleaned string or raises."""
    parts = [p.strip().lower() for p in platforms_str.split(",") if p.strip()]
    unknown = set(parts) - _KNOWN_PLATFORMS
    if unknown:
        raise ValueError(
            f"Unknown platform(s): {', '.join(sorted(unknown))}. "
            f"Valid: {', '.join(sorted(_KNOWN_PLATFORMS))}"
        )
    return ",".join(parts)


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
    elif key == "output_format":
        cfg.output_format = value
    elif key == "default_platforms":
        value = _validate_platforms(value)
        cfg.default_platforms = value
    elif key == "timezone":
        value = _validate_timezone(value)
        cfg.timezone = value
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
