"""Explicit, separate, one-time handle sharing. Inactive pending backend review."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit

import click
import httpx

from typefully_cli.config import Config
from typefully_cli.console import write_success
from typefully_cli.exceptions import TypefullyError
from typefully_cli.telemetry import CI_VARIABLES

# Intentionally inactive: recipient/storage approval and a separate release are required.
# This must be a separately deployed service, never the aggregate telemetry endpoint.
HANDLE_ENDPOINT = ""
CONSENT_REVISION = "1"
RETENTION_DAYS = 90


def _invalid(message: str) -> None:
    raise TypefullyError(message, code="invalid_input")


def _base_url() -> str:
    try:
        parsed = urlsplit(HANDLE_ENDPOINT)
        valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username
                 and not parsed.password and parsed.path in {"", "/"}
                 and not parsed.query and not parsed.fragment and parsed.port in {None, 443})
    except ValueError:
        valid = False
    if not valid:
        _invalid("Optional handle sharing is not activated in this build.")
    return HANDLE_ENDPOINT.rstrip("/")


def _receipt_path() -> Path:
    # Construct the path without loading API credentials or account settings.
    return Config()._path.parent / "handle-sharing.json"


def _interactive() -> bool:
    return (all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))
            and not any(os.environ.get(name) for name in CI_VARIABLES))


def normalize_handle(value: str) -> str:
    handle = value.strip().removeprefix("@").lower()
    # Existing short handles are allowed; this is syntax validation, not ownership verification.
    if not re.fullmatch(r"[a-z0-9_]{1,15}", handle, flags=re.ASCII):
        _invalid("Enter an X handle of 1-15 letters, numbers or underscores; no URL.")
    return handle


def _disclosure(base_url: str) -> str:
    recipient = base_url or "Not activated; no recipient is configured in this draft"
    return (
        "Optional X handle sharing with Dheeraj Shah, the Typefully CLI maintainer.\n"
        "Purpose: understand who chooses to use this CLI. Sharing is off by default.\n"
        "Only the handle you enter, consent revision, and a random withdrawal token\n"
        "are sent once to " + recipient + ".\n"
        "The service stores your handle, a hash of the token, consent revision and\n"
        "90-day expiry, separately from usage counts. It does not link command history.\n"
        "The host receives your network IP. Application request logging stays disabled.\n"
        "Expired entries are hidden at 90 days and removed within the next daily cleanup;\n"
        "provider backups may retain deleted data temporarily.\n"
        "Withdraw with: typefully community withdraw-handle\n"
        "Keep your local handle-sharing.json receipt for withdrawal.\n"
        "This is self-reported, does not verify ownership, and is not marketing consent.\n"
        "Anonymous usage telemetry and its opt-out controls remain independent."
    )


def _request(base_url: str, path: str, payload: dict, expected_status: int) -> None:
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False, trust_env=False) as client:
            client.headers.clear()
            with client.stream(
                "POST", base_url + path,
                headers={"Content-Type": "application/json", "User-Agent": "typefully-cli"},
                json=payload,
            ) as response:
                if response.status_code != expected_status:
                    raise ValueError("unconfirmed")
    except Exception:
        raise TypefullyError(
            "The service did not confirm this request. Your withdrawal receipt is retained.",
            code="handle_sharing_unconfirmed",
            hint="No automatic retry occurred. Run community withdraw-handle to remove any entry.",
        ) from None


def _load_receipt() -> dict:
    path = _receipt_path()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2048:
        _invalid("No usable local handle-sharing receipt. Entries otherwise expire after 90 days.")
    try:
        receipt = json.loads(path.read_text())
    except (ValueError, OSError):
        _invalid("The local withdrawal receipt could not be read.")
    if (not isinstance(receipt, dict) or receipt.get("endpoint") != _base_url()
            or not isinstance(receipt.get("withdrawal_token"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", receipt.get("withdrawal_token", ""))):
        _invalid("The local withdrawal receipt is invalid or belongs to another recipient.")
    return receipt


def register_commands(cli, shared_options, error_handler):
    @cli.group("community")
    def community():
        """Optional, explicit sharing with the maintainer; separate from usage counts."""

    @community.command("privacy")
    @shared_options
    @error_handler
    def privacy(**options):
        """Show the handle-sharing purpose, fields, retention and withdrawal path."""
        if options.get("use_json"):
            write_success({"active": bool(HANDLE_ENDPOINT), "disclosure": _disclosure(HANDLE_ENDPOINT)})
        else:
            click.echo(_disclosure(HANDLE_ENDPOINT))

    @community.command("share-handle")
    @shared_options
    @error_handler
    def share_handle(**options):
        """Voluntarily enter and confirm your own X handle for one-time sharing."""
        base_url = _base_url()
        if (not _interactive() or any(options.get(key) for key in ("use_json", "quiet", "debug"))):
            _invalid("Share a handle from an interactive terminal without --json, --quiet or --debug.")
        path = _receipt_path()
        if path.exists() or path.is_symlink():
            _invalid("A withdrawal receipt already exists. Withdraw before submitting another handle.")
        click.echo(_disclosure(base_url), err=True)
        try:
            handle = normalize_handle(click.prompt("Your own X handle"))
            confirmed = click.confirm(f"Send @{handle} to Dheeraj Shah for this purpose?", default=False)
        except click.Abort:
            confirmed = False
        if not confirmed:
            write_success({"shared": False})
            return
        token = secrets.token_hex(32)
        receipt = {"endpoint": base_url, "handle": handle, "withdrawal_token": token}
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Save withdrawal capability before the request, including uncertain responses.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as stream:
            json.dump(receipt, stream)
            stream.flush()
            os.fsync(stream.fileno())
        _request(base_url, "/v1/share", {
            "handle": handle, "withdrawal_token": token, "consent_revision": CONSENT_REVISION,
        }, 201)
        write_success({"shared": True, "handle": handle, "retention_days": RETENTION_DAYS})

    @community.command("withdraw-handle")
    @shared_options
    @error_handler
    def withdraw_handle(**options):
        """Delete the shared entry using the local receipt, then remove that receipt."""
        receipt = _load_receipt()
        _request(receipt["endpoint"], "/v1/withdraw", {
            "withdrawal_token": receipt["withdrawal_token"],
        }, 204)
        _receipt_path().unlink()
        write_success({"withdrawn": True})
