"""Best-effort aggregate usage with a disclosed, maintainer-owned collector."""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlsplit

import click
import httpx

from typefully_cli import __version__
from typefully_cli.config import Config

# Maintainer-owned recipient; changing it requires a new visible notice.
ENDPOINT = "https://typefully-cli-telemetry.dheeraj-personal-site.workers.dev/v1/count"
NOTICE_REVISION = "1"
COMMAND_CATEGORIES = {
    "me": "account", "accounts": "account", "account-detail": "account",
    "linkedin-resolve": "account",
    "recent": "drafts", "draft": "drafts", "thread": "drafts", "get": "drafts",
    "open": "drafts", "update": "drafts", "delete": "drafts", "drafts": "drafts",
    "batch": "drafts", "plan": "drafts",
    "publish": "publishing", "schedule": "publishing",
    "upload": "media", "media-status": "media",
    "tags": "tags", "tag-create": "tags",
    "analytics": "analytics", "followers": "analytics",
    "comments": "comments", "queue": "queue", "queue-schedule": "queue",
}
CI_VARIABLES = ("CI", "GITHUB_ACTIONS", "GITLAB_CI", "JENKINS_URL", "BUILD_BUILDID", "TF_BUILD")


def record_usage(command: str | None, *, quiet: bool = False) -> None:
    """Count a known command, never its arguments, without affecting its outcome."""
    try:
        category = COMMAND_CATEGORIES.get(command)
        if not ENDPOINT or category is None or quiet:
            return
        if any(os.environ.get(key) for key in CI_VARIABLES):
            return
        if os.environ.get("TYPEFULLY_TELEMETRY", "").lower() in {"0", "false", "off", "no"}:
            return
        # Never collect from scripts, agents, redirected output, or background jobs.
        if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
            return
        endpoint = urlsplit(ENDPOINT)
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
            return
        if endpoint.query or endpoint.fragment or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", __version__):
            return
        cfg = Config.load()
        if not cfg.telemetry_enabled or cfg.output_format == "json":
            return
        marker = cfg._path.parent / "telemetry-notice"
        notice_key = NOTICE_REVISION + "\n" + ENDPOINT + "\n"
        if not marker.is_file() or marker.read_text() != notice_key:
            click.echo(
                "Typefully CLI usage telemetry is enabled by default for later interactive runs.\n"
                "Only CLI version and command category are sent to " + ENDPOINT + ".\n"
                "No content, arguments, API keys, account details, or persistent device ID are sent.\n"
                "The host sees your network IP; the collector stores only aggregate counts, "
                "not IPs or user agents. This is activity measurement, not unique users.\n"
                "Nothing is sent on this run. Before your next run, opt out with\n"
                "TYPEFULLY_TELEMETRY=0 or: typefully config set telemetry_enabled false",
                err=True,
            )
            # Keep disclosure state separate: never rewrite auth config just to record a notice.
            marker.parent.mkdir(parents=True, exist_ok=True)
            with marker.open("w") as handle:
                os.chmod(marker, 0o600)
                handle.write(notice_key)
            return
        # Dedicated transport: no Typefully auth, proxy credentials, redirects, or retries.
        with httpx.Client(timeout=0.2, follow_redirects=False, trust_env=False) as client:
            client.headers.clear()
            with client.stream(
                "POST", ENDPOINT,
                headers={"Content-Type": "application/json", "User-Agent": "typefully-cli"},
                json={"version": __version__, "category": category},
            ):
                pass  # Do not consume a response body or follow server instructions.
    except Exception:
        # Telemetry must never fail the user's command or print sensitive transport errors.
        return
