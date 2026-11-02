"""Explicit ongoing sharing of public connected profiles; inactive pending approval."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import click
import httpx

from typefully_cli.auth import resolve_api_key
from typefully_cli.config import Config
from typefully_cli.console import write_success
from typefully_cli.exceptions import TypefullyError
from typefully_cli.telemetry import CI_VARIABLES, COMMAND_CATEGORIES

# No service is activated by this draft. Bind the approved fixed recipient and disclosure together.
PROFILE_ENDPOINT = ""
CONSENT_REVISION = "3"
SYNC_INTERVAL = 86400
RETENTION_DAYS = 90
LOOKUP_BUDGET = 10.0
MAX_SETS = 100
MAX_PROFILES = 600
MAX_SNAPSHOT_BYTES = 65536
API_ORIGIN = "https://api.typefully.com"
PLATFORMS = ("x", "linkedin", "bluesky", "threads", "mastodon", "substack")
RESERVED_TLDS = {"local", "localhost", "internal", "invalid", "test", "example", "onion", "alt", "arpa"}


def _error(message: str, code: str = "invalid_input") -> None:
    raise TypefullyError(message, code=code)


def _base_url() -> str:
    try:
        parsed = urlsplit(PROFILE_ENDPOINT)
        valid = (parsed.scheme == "https" and parsed.hostname and parsed.username is None
                 and parsed.password is None and parsed.path in {"", "/"}
                 and not parsed.query and not parsed.fragment and parsed.port in {None, 443})
    except ValueError:
        valid = False
    if not valid:
        _error("Connected profile sharing is not activated in this build.")
    return PROFILE_ENDPOINT.rstrip("/")


def _state_path() -> Path:
    return Config()._path.parent / "profile-sharing.json"


def _stop_path() -> Path:
    return _state_path().with_name("profile-sharing-disabled")


def _interactive() -> bool:
    return (all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr))
            and not any(os.environ.get(key) for key in CI_VARIABLES))


def _read_state() -> dict | None:
    path = _state_path()
    if not path.exists() and not path.is_symlink():
        return None
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > 4096
            or (os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077)):
        _error("Profile-sharing receipt is unusable. Sync is disabled; keep it for removal.")
    try:
        state = json.loads(path.read_text())
    except (ValueError, OSError):
        _error("Profile-sharing receipt is unreadable. Sync is disabled.")
    if (not isinstance(state, dict) or state.get("endpoint") != _base_url()
            or not isinstance(state.get("token"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", state["token"])
            or type(state.get("enabled")) is not bool
            or type(state.get("last_attempt")) is not int
            or state["last_attempt"] < 0):
        _error("Profile-sharing receipt is invalid or belongs to another recipient. Sync is disabled.")
    return state


def _save_state(state: dict) -> None:
    path = _state_path()
    if path.is_symlink():
        _error("Profile-sharing receipt must not be a symlink.")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".profile-sharing-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _lock():
    path = _state_path().with_name("profile-sharing.lock")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        _error("Profile-sharing lock must not be a symlink.")
    with os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+b") as stream:
        try:
            if os.name == "nt":
                import msvcrt
                if path.stat().st_size == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            _error("A profile sync is running. Local revocation remains effective; retry removal shortly.",
                   "profile_sync_busy")
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def _disable_locally() -> None:
    path = _stop_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        _error("Profile-sharing stop marker must not be a symlink.")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
        stream.write("disabled\n")
        stream.flush()
        os.fsync(stream.fileno())


def _public_url(value: str, platform: str) -> bool:
    if (not isinstance(value, str) or not 1 <= len(value) <= 2048
            or any(ord(char) < 33 or ord(char) == 127 for char in value)
            or "\\" in value or re.search(r"%(?:00|0a|0d)", value, re.I)):
        return False
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.query
                or parsed.fragment or parsed.port not in {None, 443} or not parsed.path.strip("/")
                or len(host) > 253 or not host.isascii()):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        labels = host.lower().split(".")
        if (len(labels) < 2 or labels[-1] in RESERVED_TLDS or not labels[-1][0].isalpha()
                or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x)
                       for x in labels)):
            return False
        allowed = {
            "x": ("x.com", "twitter.com"), "linkedin": ("linkedin.com",),
            "bluesky": ("bsky.app",), "threads": ("threads.net", "threads.com"),
            "substack": ("substack.com",),
        }
        return platform == "mastodon" or any(
            host == domain or host.endswith("." + domain) for domain in allowed.get(platform, ())
        )
    except (ValueError, IndexError):
        return False


def _project_profiles(detail: dict) -> list[dict]:
    platforms = detail.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != set(PLATFORMS):
        _error("Connected profile metadata is incomplete or has an unsupported platform.", "profile_lookup_failed")
    profiles = []
    for platform in PLATFORMS:
        account = platforms.get(platform)
        if account is None:
            continue
        if not isinstance(account, dict) or account.get("platform", platform) != platform:
            _error("Connected profile metadata is invalid.", "profile_lookup_failed")
        username, url = account.get("username"), account.get("profile_url")
        if username is not None and (not isinstance(username, str) or not 1 <= len(username) <= 256
                                     or any(char.isspace() or ord(char) < 33 or ord(char) == 127
                                            for char in username)):
            _error("A public username is unavailable or invalid; no snapshot was sent.", "profile_lookup_failed")
        if url is not None and not _public_url(url, platform):
            _error("A public profile URL is unavailable or invalid; no snapshot was sent.", "profile_lookup_failed")
        if (platform != "substack" and (username is None or url is None)) or (username is None and url is None):
            _error("A connected profile lacks a public identifier; no snapshot was sent.", "profile_lookup_failed")
        profile = {"platform": platform}
        if username is not None:
            profile["username"] = username
        if url is not None:
            profile["profile_url"] = url
        profiles.append(profile)
    return profiles


def _api_get(client, path: str, deadline: float, **params) -> dict:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _error("Profile lookup time budget exceeded; no snapshot was sent.", "profile_lookup_failed")
    with client.stream("GET", API_ORIGIN + path, params=params or None,
                       timeout=min(2.0, remaining)) as response:
        if response.status_code != 200:
            _error("Typefully did not confirm a complete profile lookup.", "profile_lookup_failed")
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=16384):
            body.extend(chunk)
            if len(body) > 1048576 or time.monotonic() > deadline:
                _error("Profile lookup exceeded its bounds; no snapshot was sent.", "profile_lookup_failed")
        value = json.loads(body)
        if not isinstance(value, dict):
            _error("Typefully profile metadata is invalid.", "profile_lookup_failed")
        return value


def _collect_profiles(key: str) -> list[dict]:
    deadline = time.monotonic() + LOOKUP_BUDGET
    with httpx.Client(timeout=2.0, follow_redirects=False, trust_env=False) as client:
        client.headers.clear()
        client.headers.update({"Authorization": "Bearer " + key, "User-Agent": "typefully-cli"})
        ids, count = [], None
        while True:
            page = _api_get(client, "/v2/social-sets", deadline, limit=50, offset=len(ids))
            rows, total = page.get("results"), page.get("count")
            if (not isinstance(rows, list) or len(rows) > 50 or type(total) is not int
                    or not 0 <= total <= MAX_SETS or (count is not None and count != total)):
                _error("The complete accessible account list could not be read within bounds.", "profile_lookup_failed")
            count = total
            for row in rows:
                identifier = row.get("id") if isinstance(row, dict) else None
                if type(identifier) is not int or identifier < 1 or identifier in ids:
                    _error("The accessible account list changed or is invalid.", "profile_lookup_failed")
                ids.append(identifier)
            if len(ids) == count:
                break
            if len(ids) > count or len(rows) < 50:
                _error("The accessible account list is incomplete.", "profile_lookup_failed")
        profiles, seen = [], set()
        for identifier in ids:
            detail = _api_get(client, f"/v2/social-sets/{identifier}/", deadline)
            if type(detail.get("id")) is not int or detail["id"] != identifier:
                _error("Typefully returned inconsistent account metadata.", "profile_lookup_failed")
            for profile in _project_profiles(detail):
                signature = json.dumps(profile, sort_keys=True)
                if signature not in seen:
                    profiles.append(profile)
                    seen.add(signature)
        if len(profiles) > MAX_PROFILES or len(json.dumps(profiles).encode()) > MAX_SNAPSHOT_BYTES:
            _error("The complete profile snapshot exceeds its reviewed bounds.", "profile_lookup_failed")
        return profiles


def _submit(path: str, payload: dict, expected: int) -> None:
    with httpx.Client(timeout=2.0, follow_redirects=False, trust_env=False) as client:
        client.headers.clear()
        with client.stream("POST", _base_url() + path, headers={
            "Content-Type": "application/json", "User-Agent": "typefully-cli",
        }, json=payload) as response:
            if path in {"/v1/register", "/v1/sync"} and response.status_code == 410:
                _disable_locally()
            if response.status_code != expected:
                _error("The service did not confirm the request. Keep the receipt for withdrawal.",
                       "profile_submission_unconfirmed")


def _sync_locked(state: dict, key: str | None = None, explicit: bool = False) -> bool:
    now = int(time.time())
    if (_stop_path().exists() or not state["enabled"] or state.get("consent_revision") != CONSENT_REVISION
            or (state["last_attempt"] and now - state["last_attempt"] < SYNC_INTERVAL)):
        return False
    state.update(last_attempt=now, last_status="pending")
    _save_state(state)
    phase = "admission"
    try:
        # Reserve a bounded empty record before any identity lookup. Sync cannot create records.
        _submit("/v1/register", {"withdrawal_token": state["token"], "consent_revision": CONSENT_REVISION,
                                 "requested_at": now}, 201)
        if _stop_path().exists():
            state.update(enabled=False, last_status="stopped")
            _save_state(state)
            return False
        phase = "lookup"
        if key is None:
            cfg = Config.load()
            if explicit:
                key = resolve_api_key(None, os.environ.get("TYPEFULLY_API_KEY"), cfg)
            else:
                key = os.environ.get("TYPEFULLY_API_KEY") or cfg.api_key
        if not key:
            _error("Profile sync needs the existing Typefully API key.", "profile_lookup_failed")
        profiles = _collect_profiles(key)
        # Revocation is effective locally even while another process is still looking up profiles.
        current = _read_state()
        if _stop_path().exists() or current is None or not current["enabled"]:
            state.update(enabled=False, last_status="stopped")
            _save_state(state)
            return False
        phase = "submit"
        _submit("/v1/sync", {"profiles": profiles, "withdrawal_token": state["token"],
                            "consent_revision": CONSENT_REVISION, "snapshot_at": int(time.time())}, 201)
        state.update(last_success=int(time.time()), last_status="synced", profile_count=len(profiles))
        _save_state(state)
        return True
    except Exception as error:
        state["last_status"] = {"lookup": "lookup_failed", "admission": "admission_unconfirmed"}.get(
            phase, "submission_unconfirmed")
        _save_state(state)
        if explicit:
            if phase == "admission":
                message = "Collector admission was not confirmed. No new identity lookup was performed."
            elif phase == "lookup":
                message = (str(error) if isinstance(error, TypefullyError)
                           and error.code == "profile_lookup_failed"
                           else "Profile lookup failed. No new snapshot was sent.")
            else:
                message = "Profile submission was not confirmed. Keep the receipt for withdrawal."
            _error(message + " No automatic sync attempt for 24 hours; check community status.",
                   "profile_sync_unconfirmed")
        return False


def maybe_sync_profiles(command: str | None, *, api_key: str | None = None,
                        quiet: bool = False, debug: bool = False) -> None:
    """Best effort after eligible successful commands; never change the command's outcome."""
    try:
        if (not PROFILE_ENDPOINT or command not in COMMAND_CATEGORIES or quiet or debug
                or not _interactive() or _stop_path().exists()):
            return
        state = _read_state()
        if (state is None or not state["enabled"] or state.get("consent_revision") != CONSENT_REVISION
                or (state["last_attempt"] and int(time.time()) - state["last_attempt"] < SYNC_INTERVAL)):
            return
        if Config.load().output_format == "json":
            return
        with _lock():
            current = _read_state()
            if current is not None:
                _sync_locked(current, key=api_key)
    except Exception:
        return


def _disclosure() -> str:
    return (
        "Optional ongoing profile sharing with Dheeraj Shah, the Typefully CLI maintainer.\n"
        "Purpose: understand who uses the CLI. Off by default.\n"
        "ONE opt-in covers ALL accounts your API key can access, including team/client\n"
        "accounts and profiles connected later: X, LinkedIn, Bluesky, Threads, Mastodon, Substack.\n"
        "Confirm you have permission to share those managed/client profiles.\n"
        "After consent we first send the random withdrawal token, consent revision and\n"
        "request time to reserve capacity. Only confirmed admission allows profile lookup.\n"
        "We read the documented public usernames and profile URLs from Typefully, then\n"
        "send only platform, username/URL, consent revision, snapshot time and a random\n"
        "withdrawal token to " + (PROFILE_ENDPOINT or "[inactive: no recipient configured]") + ".\n"
        "Your API key goes only to Typefully; no names, emails, posts, messages, avatars\n"
        "or internal account IDs go to the maintainer. Profile URLs are never fetched.\n"
        "Sync runs at most once per 24 hours during later eligible interactive use.\n"
        "No daemon. CI, scripts, JSON, quiet, debug, config and help/version do not sync.\n"
        "Consent continues until withdrawn. Each successful sync replaces the previous\n"
        "snapshot and resets its 90-day expiry; active use can retain current profiles\n"
        "indefinitely. Expired data is removed at daily cleanup; backups may last longer.\n"
        "The host sees your network IP; application request logging stays disabled.\n"
        "Run: typefully community withdraw-profiles to stop sync locally immediately\n"
        "and delete the remote profiles. Keep your private profile-sharing.json receipt.\n"
        "A token hash remains for 90 days after withdrawal to block delayed uploads.\n"
        "Public identifiers/ownership are not independently verified; no marketing consent.\n"
        "Anonymous activity telemetry and its opt-out controls remain separate."
    )


def register_commands(cli, shared_options, error_handler):
    @cli.group("community")
    def community():
        """Explicit optional profile sharing, status and withdrawal."""

    @community.command("privacy")
    @shared_options
    @error_handler
    def privacy(**options):
        """Show recipient, scope, ongoing sync, retention and removal."""
        if options.get("use_json"):
            write_success({"active": bool(PROFILE_ENDPOINT), "disclosure": _disclosure()})
        else:
            click.echo(_disclosure())

    @community.command("share-profiles")
    @shared_options
    @error_handler
    def share_profiles(**options):
        """Opt in once for all accessible accounts, including profiles linked later."""
        _base_url()
        if options.get("account"):
            _error("Profile sharing covers ALL accessible accounts; --account cannot limit this scope.")
        if not _interactive() or any(options.get(k) for k in ("use_json", "quiet", "debug")):
            _error("Opt in from an interactive terminal without --json, --quiet or --debug.")
        if _state_path().exists() or _state_path().is_symlink():
            _error("A profile-sharing receipt exists. Use status, sync-profiles or withdraw-profiles.")
        click.echo(_disclosure(), err=True)
        try:
            confirmed = click.confirm(
                "Enable ongoing sharing of ALL accessible profiles and confirm permission for team/client profiles?",
                default=False,
            )
        except click.Abort:
            confirmed = False
        if not confirmed:
            write_success({"enabled": False})
            return
        with _lock():
            if _state_path().exists() or _state_path().is_symlink():
                _error("Another profile-sharing receipt already exists.")
            state = {"endpoint": _base_url(), "token": secrets.token_hex(32), "enabled": True,
                     "consent_revision": CONSENT_REVISION, "last_attempt": 0, "last_status": "pending"}
            _save_state(state)
            _stop_path().unlink(missing_ok=True)
            synced = _sync_locked(state, key=options.get("api_key"), explicit=True)
            write_success({"enabled": not _stop_path().exists(), "synced": synced,
                           "profile_count": state.get("profile_count", 0)})

    @community.command("sync-profiles")
    @shared_options
    @error_handler
    def sync_profiles(**options):
        """Sync a due full snapshot under existing consent (at most once per 24h)."""
        if options.get("account"):
            _error("Profile sharing covers ALL accessible accounts; --account cannot limit this scope.")
        if not _interactive() or any(options.get(k) for k in ("use_json", "quiet", "debug")):
            _error("Sync from an interactive terminal without --json, --quiet or --debug.")
        with _lock():
            state = _read_state()
            if (state is None or not state["enabled"] or _stop_path().exists()
                    or state.get("consent_revision") != CONSENT_REVISION):
                _error("Profile sharing is disabled. Use share-profiles for explicit consent.")
            synced = _sync_locked(state, key=options.get("api_key"), explicit=True)
            write_success({"enabled": not _stop_path().exists(), "synced": synced,
                           "next_sync_after": state["last_attempt"] + SYNC_INTERVAL})

    @community.command("status")
    @shared_options
    @error_handler
    def status(**options):
        """Show local consent/sync status without account lookup or token output."""
        state = _read_state() if PROFILE_ENDPOINT else None
        enabled = bool(state and state["enabled"] and not _stop_path().exists()
                       and state.get("consent_revision") == CONSENT_REVISION)
        write_success({"enabled": enabled, "recipient_active": bool(PROFILE_ENDPOINT),
                       "last_status": state.get("last_status") if state else None,
                       "last_success": state.get("last_success") if state else None,
                       "deletion_receipt_present": _state_path().exists()})

    @community.command("withdraw-profiles")
    @shared_options
    @error_handler
    def withdraw_profiles(**options):
        """Stop sync immediately and remove all remote profiles using the receipt."""
        _disable_locally()
        with _lock():
            state = _read_state()
            if state is None:
                write_success({"enabled": False, "deleted": False, "reason": "no_local_receipt"})
                return
            state["enabled"] = False
            _save_state(state)
            try:
                _submit("/v1/withdraw", {"withdrawal_token": state["token"]}, 204)
            except Exception:
                _error("Sync is disabled locally. Remote deletion is unconfirmed; retain the receipt and retry withdrawal.",
                       "profile_deletion_unconfirmed")
            _state_path().unlink()
            write_success({"enabled": False, "deleted": True})
