"""API key resolution chain."""

from __future__ import annotations

import subprocess

from typefully_cli.config import Config
from typefully_cli.exceptions import AuthError


def resolve_api_key(
    cli_flag: str | None,
    env_var: str | None,
    config: Config,
) -> str:
    """Resolve API key from the priority chain.

    1. --api-key CLI flag
    2. TYPEFULLY_API_KEY env var
    3. Config file [auth] api_key
    4. 1Password (if configured)
    """
    if cli_flag:
        return cli_flag
    if env_var:
        return env_var
    if config.api_key:
        return config.api_key
    if config.onepassword_item:
        return _fetch_from_1password(config.onepassword_item)
    raise AuthError()


def _fetch_from_1password(item_name: str) -> str:
    """Fetch API key from 1Password CLI."""
    try:
        result = subprocess.run(
            ["op", "item", "get", item_name, "--fields", "password", "--reveal"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise AuthError(
            "1Password CLI (op) not found",
            hint="Install 1Password CLI or use a different auth method",
        )
    except subprocess.TimeoutExpired:
        raise AuthError("1Password CLI timed out")

    key = result.stdout.strip()
    if not key or result.returncode != 0:
        raise AuthError(
            f"Could not retrieve key from 1Password item '{item_name}'",
            hint="Check that the item exists and 1Password CLI is unlocked",
        )
    return key
