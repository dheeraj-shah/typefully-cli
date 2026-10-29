"""Click CLI: all 17 commands with shared per-subcommand options."""

from __future__ import annotations

import csv
import datetime
import io
import json
import os
import sys
from functools import wraps
from typing import Any
from urllib.parse import urlsplit

import click

from typefully_cli import __version__
from typefully_cli.auth import resolve_api_key
from typefully_cli.batch import merge_defaults, parse_batch_file
from typefully_cli.client import TypefullyClient
from typefully_cli.config import Config, config_set
from typefully_cli.console import Console, write_success
from typefully_cli.exceptions import APIError, TypefullyError
from typefully_cli.media import upload_media
from typefully_cli import output as fmt
from typefully_cli.completions import completions
from typefully_cli.telemetry import record_usage


# --- Shared option decorator ---


def shared_options(f):
    """Add --api-key, --account, --text, --json, --quiet, --debug to a subcommand."""

    @click.option("--api-key", default=None, help="API key (overrides env/config)")
    @click.option(
        "--account", "-a", default=None, help="Account name, username, or numeric ID"
    )
    @click.option("--text", "use_text", is_flag=True, help="Human-readable output (default)")
    @click.option("--json", "use_json", is_flag=True, help="JSON output for agents/scripts")
    @click.option("--quiet", "-q", is_flag=True, help="Suppress non-error stderr")
    @click.option("--debug", is_flag=True, hidden=True, help="Log HTTP requests to stderr")
    @wraps(f)
    def wrapper(*args, **kwargs):
        ctx = click.get_current_context(silent=True)
        if ctx is not None:
            record_usage(
                ctx.find_root().invoked_subcommand,
                quiet=kwargs.get("quiet", False) or kwargs.get("use_json", False),
            )
        return f(*args, **kwargs)

    return wrapper


def _get_client_and_console(
    api_key: str | None, quiet: bool, config: Config | None = None, debug: bool = False
) -> tuple[TypefullyClient, Console, Config]:
    """Resolve auth and return client + console."""
    cfg = config or Config.load()
    console = Console(quiet=quiet)
    key = resolve_api_key(api_key, os.environ.get("TYPEFULLY_API_KEY"), cfg)
    client = TypefullyClient(api_key=key, debug=debug)
    return client, console, cfg


def _resolve_account_id(
    client: TypefullyClient,
    account: str | None,
    config: Config,
    positional: str | None = None,
) -> int:
    """Account resolution chain: positional > --account > config default."""
    value = positional or account
    return client.resolve_account(value, config.default_account)


def _handle_error(err: TypefullyError, console: Console) -> None:
    """Write structured error JSON to stderr and exit."""
    console.error_json(err.to_dict())
    if isinstance(err, TypefullyError) and err.code in ("auth_failed", "no_account", "invalid_input"):
        sys.exit(1)
    sys.exit(2)


def _validate_date(value: str, name: str) -> str:
    """Validate a YYYY-MM-DD date string. Returns the value or raises."""
    if not value:
        return value
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        raise TypefullyError(
            f"Invalid {name} date: '{value}'",
            code="invalid_input",
            hint="Expected format: YYYY-MM-DD",
        )
    return value


def _validate_limit(value: int, max_val: int = 50) -> int:
    """Validate a pagination limit is within 1..max_val."""
    if value < 1 or value > max_val:
        raise TypefullyError(
            f"Invalid limit: {value}",
            code="invalid_input",
            hint=f"Limit must be between 1 and {max_val}",
        )
    return value


def _apply_default_platforms(
    config: Config,
    linkedin: bool, threads: bool, bluesky: bool, mastodon: bool,
    all_platforms: bool,
) -> tuple:
    """Apply default platforms from config when no platform flags are explicitly set."""
    if all_platforms or linkedin or threads or bluesky or mastodon:
        return linkedin, threads, bluesky, mastodon
    if not config.default_platforms:
        return linkedin, threads, bluesky, mastodon
    for p in config.default_platforms.split(","):
        p = p.strip().lower()
        if p == "linkedin":
            linkedin = True
        elif p == "threads":
            threads = True
        elif p == "bluesky":
            bluesky = True
        elif p == "mastodon":
            mastodon = True
    return linkedin, threads, bluesky, mastodon


def _apply_timezone(schedule: str | None, config: Config) -> str | None:
    """Convert a schedule datetime to UTC if a timezone is configured and no tz info present."""
    if not schedule or schedule in ("next", "now"):
        return schedule
    if not config.timezone:
        return schedule
    # If the schedule already has timezone info (Z, +, -), leave it alone
    if schedule.endswith("Z") or "+" in schedule[10:] or schedule[10:].count("-") > 0:
        return schedule
    # Try to parse as a naive datetime and attach the configured timezone
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.datetime.fromisoformat(schedule)
    except ValueError:
        return schedule  # can't parse, let the API handle it
    if dt.tzinfo is not None:
        return schedule  # already has tz
    local_tz = ZoneInfo(config.timezone)
    local_dt = dt.replace(tzinfo=local_tz)
    utc_dt = local_dt.astimezone(datetime.timezone.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


POST_PLATFORMS = {"x", "linkedin", "threads", "bluesky", "mastodon", "substack"}
LINK_PREVIEW_PLATFORMS = {"linkedin", "threads", "substack"}


def _quote_platform(url: str, platforms: list[str]) -> str:
    """Route quotes using Typefully's official agent CLI host/path rules."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        raise TypefullyError("Quote URL must be a full HTTP(S) post URL", code="invalid_input")
    if not host or parsed.scheme not in {"http", "https"}:
        raise TypefullyError("Quote URL must be a full HTTP(S) post URL", code="invalid_input")
    known = None
    for platform, domains in {
        "x": ("x.com", "twitter.com"),
        "threads": ("threads.net", "threads.com"),
        "bluesky": ("bsky.app",),
        "substack": ("substack.com",),
    }.items():
        if any(host == domain or host.endswith("." + domain) for domain in domains):
            known = platform
            break
    if not known and "substack" in platforms and (
        "/note/c-" in parsed.path or "/p/" in parsed.path
    ):
        known = "substack"
    if known:
        if known not in platforms:
            raise TypefullyError(
                f"Quote URL requires {known} in --platform", code="invalid_input"
            )
        return known
    candidates = [p for p in platforms if p in POST_PLATFORMS and p != "linkedin"]
    if "mastodon" in candidates:
        return "mastodon"
    if len(candidates) == 1:
        return candidates[0]
    raise TypefullyError(
        "Quote URL has no unambiguous target; select X, Threads, Bluesky, Mastodon, or Substack",
        code="invalid_input",
    )


def _platform_field_options(f):
    """Optional platform fields, omitted unless explicitly supplied."""
    options = [
        click.option("--reply-settings", type=click.Choice([
            "following", "mentionedUsers", "subscribers", "verified", "null",
        ]), default=None, help="X reply audience; null restores everyone"),
        click.option("--subscribers-only/--no-subscribers-only", default=None),
        click.option("--share-with-followers/--no-share-with-followers", default=None,
                     help="Also share an X community post to followers"),
        click.option("--linkedin-first-comment", default=None,
                     help="LinkedIn first comment (max 1250 characters); null clears"),
        click.option("--linkedin-reshare-target", default=None,
                     help="LinkedIn post URL or URN (max 2048 characters); null clears"),
    ]
    for option in options:
        f = option(f)
    return f


def _validate_platform_fields(platforms, fields):
    x_fields = ("reply_settings", "subscribers_only", "share_with_followers")
    li_fields = ("linkedin_first_comment", "linkedin_reshare_target")
    for platform, names in (("x", x_fields), ("linkedin", li_fields)):
        if any(fields.get(name) is not None for name in names) and platform not in platforms:
            raise TypefullyError(
                f"{platform}-only options require {platform} in --platform", code="invalid_input"
            )
    reply = fields.get("reply_settings")
    if reply is not None and reply not in {
        "following", "mentionedUsers", "subscribers", "verified", "null",
    }:
        raise TypefullyError("Invalid X reply settings", code="invalid_input")
    for name, limit in (("linkedin_first_comment", 1250), ("linkedin_reshare_target", 2048)):
        value = fields.get(name)
        if value is not None and len(value) > limit:
            raise TypefullyError(
                f"--{name.replace('_', '-')} must be at most {limit} characters",
                code="invalid_input",
            )


def _apply_platform_fields(platforms, fields):
    """Apply explicit fields only; settings merge rather than overwrite."""
    _validate_platform_fields(platforms, fields)
    x = platforms.get("x", {})
    for name in ("reply_settings", "subscribers_only"):
        value = fields.get(name)
        if value is not None:
            for post in x.get("posts", []):
                post[name] = None if name == "reply_settings" and value == "null" else value
    share = fields.get("share_with_followers")
    if share is not None:
        settings = x.setdefault("settings", {})
        if not settings.get("community_id"):
            raise TypefullyError(
                "--share-with-followers requires an X community (use --community)",
                code="invalid_input",
            )
        settings["share_with_followers"] = share
    linkedin = platforms.get("linkedin", {})
    first_comment = fields.get("linkedin_first_comment")
    if first_comment is not None:
        linkedin.setdefault("settings", {})["first_comment"] = (
            None if first_comment == "null" else first_comment
        )
    reshare = fields.get("linkedin_reshare_target")
    if reshare is not None:
        for post in linkedin.get("posts", [])[:1]:
            post["linkedin_reshare_target"] = None if reshare == "null" else reshare


def _editable_posts(name, source_posts):
    """Copy writable fields, retaining anchors and translating response-only names."""
    allowed = {"text", "media_ids", "hide_link_preview"}
    if name == "x":
        allowed |= {"quote_post_url", "paid_partnership", "made_with_ai",
                    "subscribers_only", "reply_settings"}
    elif name == "linkedin":
        allowed.add("linkedin_reshare_target")
    else:
        allowed.add("quote_post_url")
    posts = []
    for source in source_posts:
        post = {k: v for k, v in source.items() if k in allowed}
        if name == "linkedin" and "linkedin_reshare_urn" in source:
            post["linkedin_reshare_target"] = source["linkedin_reshare_urn"]
        posts.append(post)
    return posts


def _resolve_platforms(
    client: TypefullyClient,
    social_set_id: int,
    platform: str | None,
    *,
    linkedin: bool = False,
    threads: bool = False,
    bluesky: bool = False,
    mastodon: bool = False,
    substack: bool = False,
    all_platforms: bool = False,
) -> list[str]:
    """Resolve target platforms while preserving legacy X-default behavior."""
    if platform and (all_platforms or any((linkedin, threads, bluesky, mastodon, substack))):
        raise TypefullyError(
            "--platform cannot be combined with platform flags or --all",
            code="invalid_input",
        )
    if platform:
        result = [p.strip().lower() for p in platform.split(",") if p.strip()]
    elif all_platforms:
        connected = client.get_social_set(social_set_id).get("platforms", {})
        result = [p for p in POST_PLATFORMS if p in connected and connected[p] is not None]
    else:
        result = ["x"]
        result.extend(
            p for enabled, p in (
                (linkedin, "linkedin"), (threads, "threads"), (bluesky, "bluesky"),
                (mastodon, "mastodon"), (substack, "substack"),
            ) if enabled
        )
    if not result:
        raise TypefullyError("No connected platforms found", code="invalid_input")
    unknown = set(result) - POST_PLATFORMS - {"x_article"}
    if unknown:
        raise TypefullyError(
            f"Unknown platform(s): {', '.join(sorted(unknown))}",
            code="invalid_input",
            hint="Valid: x, linkedin, threads, bluesky, mastodon, substack, x_article",
        )
    if "x_article" in result and len(result) != 1:
        raise TypefullyError("x_article is standalone and cannot be combined with other platforms", code="invalid_input")
    return list(dict.fromkeys(result))


def _resolve_text_mode(use_text: bool, use_json: bool, config: Config) -> bool:
    """Resolve output mode: --json wins, then --text, then config, then default (text)."""
    if use_json:
        return False
    if use_text:
        return True
    # Config default
    return config.output_format != "json"


def _output(data: Any, use_text: bool, text_fn: Any = None) -> None:
    """Write JSON envelope to stdout, or call text_fn for --text mode."""
    if use_text and text_fn:
        text_fn(data)
    else:
        write_success(data)


def _write_recent_csv(posts: list[dict]) -> None:
    """Write recently published posts as CSV to stdout."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "published_at", "text", "x_url"])
    for d in posts:
        text = ""
        platforms = d.get("platforms", {})
        if isinstance(platforms, dict) and "x" in platforms:
            pp = platforms.get("x", {}).get("posts", [])
            if pp:
                text = pp[0].get("text", "")
        if not text:
            text = d.get("preview", "")
        writer.writerow([
            d.get("id", ""),
            d.get("published_at", "")[:19],
            text[:280],
            d.get("x_published_url", ""),
        ])
    sys.stdout.write(buf.getvalue())


def error_handler(f):
    """Centralized error handler for all CLI commands.

    Catches TypefullyError -> structured stderr JSON + appropriate exit code.
    Catches unexpected Exception -> internal_error (no raw exception leak).
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except SystemExit:
            raise  # let sys.exit() through
        except TypefullyError as e:
            _handle_error(e, Console(kwargs.get("quiet", False)))
        except Exception:
            Console(kwargs.get("quiet", False)).error_json(
                {"code": "internal_error", "message": "Unexpected internal error"}
            )
            sys.exit(2)

    return wrapper


def _handle_multi_result(
    result: dict, errors: list, created: list,
    total: int, use_text: bool, text_fn: Any, console: Console,
) -> None:
    """Handle the three branches for multi-item commands (delete/batch)."""
    if not errors:
        # All succeed
        if use_text and text_fn:
            text_fn(result)
        else:
            write_success(result)
    elif created:
        # Partial failure: some succeeded, some failed
        if use_text and text_fn:
            text_fn(result)
        else:
            write_success(result)
        console.error_json({
            "code": "partial_failure",
            "status": 3,
            "message": f"{len(errors)} of {total} operations failed",
            "hint": "Check stdout data for details",
        })
        sys.exit(3)
    else:
        # All failed: nothing on stdout
        console.error_json({
            "code": "all_failed",
            "status": 2,
            "message": f"All {total} operations failed",
        })
        sys.exit(2)


# --- CLI Group ---


@click.group()
@click.version_option(__version__, prog_name="typefully")
def cli():
    """Typefully CLI -- manage drafts, threads, and publishing."""


# --- Config commands ---


cli.add_command(completions)


@cli.group()
def config():
    """Manage configuration (~/.config/typefully/config.toml)."""


@config.command("set")
@click.argument("key")
@click.argument("value")
@error_handler
def config_set_cmd(key: str, value: str, **kwargs):
    """Set a config value. Keys: api_key, default_account, default_platforms, timezone, onepassword_item."""
    cfg = Config.load()
    result = config_set(cfg, key, value)
    write_success(result)


@config.command("show")
@error_handler
def config_show_cmd(**kwargs):
    """Show current configuration (secrets redacted)."""
    cfg = Config.load()
    write_success(cfg.to_dict(redact=True))


@config.command("path")
@error_handler
def config_path_cmd(**kwargs):
    """Print the config file path."""
    cfg = Config.load()
    write_success({"path": str(cfg._path)})


@config.command("init")
@error_handler
def config_init_cmd(**kwargs):
    """Interactive setup wizard. Prompts for API key and default account."""
    cfg = Config.load()
    if cfg.api_key:
        if not click.confirm("Config already exists. Overwrite?", default=False):
            click.echo("Aborted.")
            return

    api_key = click.prompt("API key (from typefully.com/settings/api)", type=str)
    # Validate by calling /me
    console = Console(quiet=False)
    console.status("Validating API key...")
    try:
        client = TypefullyClient(api_key=api_key)
        with client:
            user = client.me()
        console.success(f"Authenticated as {user.get('name', 'unknown')}")
    except TypefullyError:
        console.error_json({"code": "auth_failed", "message": "Invalid API key"})
        sys.exit(1)

    default_account = click.prompt("Default account (name or username, optional)", default="", show_default=False)

    config_set(cfg, "api_key", api_key)
    if default_account:
        config_set(cfg, "default_account", default_account)

    write_success({"message": "Config saved", "path": str(cfg._path)})


# --- me ---


@cli.command()
@shared_options
@error_handler
def me(api_key, account, use_text, use_json, quiet, debug):
    """Show current authenticated user."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        data = client.me()
        _output(data, use_text, fmt.print_user)


# --- accounts ---


@cli.command()
@shared_options
@error_handler
def accounts(api_key, account, use_text, use_json, quiet, debug):
    """List connected social sets."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        sets = client.get_social_sets()
        if use_text:
            fmt.print_accounts(sets)
        else:
            write_success(sets)


# --- account-detail ---


@cli.command("account-detail")
@click.argument("name", required=False, default=None)
@shared_options
@error_handler
def account_detail(name, api_key, account, use_text, use_json, quiet, debug):
    """Show details for an account. NAME is optional (falls back to --account or config default)."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg, positional=name)
        data = client.get_social_set(ssid)
        _output(data, use_text, fmt.print_account_detail)


# --- recent ---


@cli.command()
@click.option("-n", "--limit", default=3, type=int, help="Number of posts (default: 3, max: 50)")
@click.option("--since", default="", help="Start date YYYY-MM-DD")
@click.option("--until", "until_date", default="", help="End date YYYY-MM-DD")
@click.option("--format", "output_format", default=None, type=click.Choice(["csv"]), help="Output format")
@shared_options
@error_handler
def recent(limit, since, until_date, output_format, api_key, account, use_text, use_json, quiet, debug):
    """List recently published posts."""
    _validate_limit(limit)
    since = _validate_date(since, "--since")
    until_date = _validate_date(until_date, "--until")
    if since and until_date and since > until_date:
        raise TypefullyError(
            f"--since ({since}) is after --until ({until_date})",
            code="invalid_input",
            hint="--since must be before or equal to --until",
        )
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        posts = client.list_recent(ssid, limit=limit, since=since, until=until_date)
        if output_format == "csv":
            _write_recent_csv(posts)
        elif use_text:
            fmt.print_recent(posts)
        else:
            write_success(posts)


# --- draft ---


@cli.command()
@click.argument("text", required=False, default=None)
@click.option("--file", "-f", "input_file", default=None, type=click.Path(exists=True),
              help="Read post content from a file")
@click.option("--schedule", default=None, help="ISO datetime, 'next', or 'now'")
@click.option("--plan", default=None, help="ISO datetime or 'next'; calendar only, does not publish")
@click.option("--tag", "tags", multiple=True, help="Tag name (repeatable, auto-created)")
@click.option("--title", default=None)
@click.option("--media", default=None, help="Comma-separated media IDs")
@click.option("--share/--no-share", default=False)
@click.option("--reply-to", default=None, help="URL of tweet to reply to")
@click.option("--scratchpad", default=None, help="Internal notes (not published)")
@click.option(
    "--qrt", "--quote-post-url", "qrt", default=None,
    help="Quote URL for X, Threads, Bluesky, Mastodon, or Substack",
)
@click.option("--threadify/--no-threadify", default=False)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--linkedin", is_flag=True)
@click.option("--threads", is_flag=True)
@click.option("--bluesky", is_flag=True)
@click.option("--mastodon", is_flag=True)
@click.option("--all", "all_platforms", is_flag=True, help="Post to all connected platforms")
@click.option("--community", default=None, help="X community ID")
@click.option("--platform", default=None, help="Comma-separated target platforms")
@click.option("--substack", is_flag=True, help="Enable Substack Notes")
@click.option("--content-markdown", default=None, help="X Article markdown (requires --platform x_article)")
@click.option("--cover-media-id", default=None, help="X Article cover media ID")
@click.option("--paid-partnership", is_flag=True, help="Add X paid-partnership disclosure")
@click.option("--made-with-ai", is_flag=True, help="Add X AI disclosure")
@click.option("--hide-link-preview", is_flag=True, help="Hide link preview on LinkedIn, Threads, Substack")
@_platform_field_options
@shared_options
@error_handler
def draft(
    text, input_file, schedule, plan, tags, title, media, share, reply_to, scratchpad,
    qrt, threadify, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon, all_platforms, community, platform, substack,
    content_markdown, cover_media_id, paid_partnership, made_with_ai, hide_link_preview,
    reply_settings, subscribers_only, share_with_followers,
    linkedin_first_comment, linkedin_reshare_target,
    api_key, account, use_text, use_json, quiet, debug,
):
    """Create a draft post."""
    platform_fields = dict(
        reply_settings=reply_settings, subscribers_only=subscribers_only,
        share_with_followers=share_with_followers,
        linkedin_first_comment=linkedin_first_comment,
        linkedin_reshare_target=linkedin_reshare_target,
    )

    if input_file:
        with open(input_file, encoding="utf-8") as fh:
            text = fh.read().strip()
    if schedule and plan:
        raise TypefullyError("--schedule and --plan are mutually exclusive", code="invalid_input")
    if not text and not content_markdown:
        raise TypefullyError(
            "No text provided", code="invalid_input",
            hint="Pass text as argument or use --file",
        )
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    schedule = _apply_timezone(schedule, cfg)
    linkedin, threads, bluesky, mastodon = _apply_default_platforms(
        cfg, linkedin, threads, bluesky, mastodon, all_platforms,
    )
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        target_platforms = _resolve_platforms(
            client, ssid, platform, linkedin=linkedin, threads=threads, bluesky=bluesky,
            mastodon=mastodon, substack=substack, all_platforms=all_platforms,
        )

        # Tag auto-creation
        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload = _build_draft_payload(
            posts_text=[text] if text else [], schedule=schedule, plan=plan, tags=list(tags),
            title=title, media=media, share=share, reply_to=reply_to,
            scratchpad=scratchpad, threadify=threadify,
            auto_retweet=auto_retweet, auto_plug=auto_plug,
            quote_post_url=qrt, community=community, platforms=target_platforms,
            content_markdown=content_markdown, cover_media_id=cover_media_id,
            paid_partnership=paid_partnership, made_with_ai=made_with_ai,
            hide_link_preview=hide_link_preview, **platform_fields,
        )

        console.status("Creating draft...")
        data = client.create_draft(ssid, payload)
        _output(data, use_text, fmt.print_draft_short)


# --- thread ---


@cli.command()
@click.argument("posts", nargs=-1, required=True)
@click.option("--schedule", default=None, help="ISO datetime, 'next', or 'now'")
@click.option("--tag", "tags", multiple=True, help="Tag name (repeatable)")
@click.option("--title", default=None)
@click.option("--media", default=None, help="Comma-separated media IDs (first post)")
@click.option("--share/--no-share", default=False)
@click.option("--reply-to", default=None)
@click.option("--scratchpad", default=None)
@click.option(
    "--qrt", "--quote-post-url", "qrt", default=None,
    help="Quote URL for X, Threads, Bluesky, Mastodon, or Substack",
)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--linkedin", is_flag=True)
@click.option("--threads", is_flag=True)
@click.option("--bluesky", is_flag=True)
@click.option("--mastodon", is_flag=True)
@click.option("--all", "all_platforms", is_flag=True, help="Post to all connected platforms")
@click.option("--community", default=None, help="X community ID")
@click.option("--platform", default=None, help="Comma-separated target platforms")
@click.option("--substack", is_flag=True, help="Enable Substack Notes")
@click.option("--paid-partnership", is_flag=True, help="Add X paid-partnership disclosure")
@click.option("--made-with-ai", is_flag=True, help="Add X AI disclosure")
@click.option("--hide-link-preview", is_flag=True, help="Hide link preview on LinkedIn, Threads, Substack")
@_platform_field_options
@shared_options
@error_handler
def thread(
    posts, schedule, tags, title, media, share, reply_to, scratchpad,
    qrt, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon, all_platforms, community, platform, substack,
    paid_partnership, made_with_ai, hide_link_preview,
    reply_settings, subscribers_only, share_with_followers,
    linkedin_first_comment, linkedin_reshare_target,
    api_key, account, use_text, use_json, quiet, debug,
):
    """Create a multi-post thread. Provide 2+ posts as separate arguments."""
    platform_fields = dict(
        reply_settings=reply_settings, subscribers_only=subscribers_only,
        share_with_followers=share_with_followers,
        linkedin_first_comment=linkedin_first_comment,
        linkedin_reshare_target=linkedin_reshare_target,
    )

    if len(posts) < 2:
        Console(quiet).error_json({
            "code": "invalid_input",
            "message": "Thread requires at least 2 posts",
            "hint": 'Usage: typefully thread "post 1" "post 2" [...]',
        })
        sys.exit(1)

    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    schedule = _apply_timezone(schedule, cfg)
    linkedin, threads, bluesky, mastodon = _apply_default_platforms(
        cfg, linkedin, threads, bluesky, mastodon, all_platforms,
    )
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        posts_list = list(posts)

        target_platforms = _resolve_platforms(
            client, ssid, platform, linkedin=linkedin, threads=threads, bluesky=bluesky,
            mastodon=mastodon, substack=substack, all_platforms=all_platforms,
        )

        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload = _build_draft_payload(
            posts_text=posts_list, schedule=schedule, tags=list(tags),
            title=title, media=media, share=share, reply_to=reply_to,
            scratchpad=scratchpad, threadify=False,
            auto_retweet=auto_retweet, auto_plug=auto_plug,
            quote_post_url=qrt, community=community, platforms=target_platforms,
            paid_partnership=paid_partnership, made_with_ai=made_with_ai,
            hide_link_preview=hide_link_preview, **platform_fields,
        )

        console.status(f"Creating {len(posts_list)}-post thread...")
        data = client.create_draft(ssid, payload)
        _output(data, use_text, fmt.print_draft_short)


# --- get ---


@cli.command()
@click.argument("draft_id")
@click.option(
    "--exclude-comment-markers",
    is_flag=True,
    help="Return display text without Typefully comment anchors",
)
@shared_options
@error_handler
def get(draft_id, exclude_comment_markers, api_key, account, use_text, use_json, quiet, debug):
    """View a specific draft."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_draft(ssid, draft_id, exclude_comment_markers=exclude_comment_markers)
        _output(data, use_text, fmt.print_draft)


# --- open ---


@cli.command("open")
@click.argument("draft_id")
@shared_options
@error_handler
def open_draft(draft_id, api_key, account, use_text, use_json, quiet, debug):
    """Open a draft in the browser."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_draft(ssid, draft_id)
        url = data.get("private_url", "")
        if not url:
            url = data.get("share_url", "")
        if not url:
            console.error_json({
                "code": "no_url",
                "message": f"No URL found for draft {draft_id}",
            })
            sys.exit(2)
        launched = click.launch(url)
        if launched != 0:
            # Fallback: print URL (e.g. over SSH with no browser)
            write_success({"url": url, "opened": False})
        else:
            write_success({"url": url, "opened": True})


# --- update ---


@cli.command()
@click.argument("draft_id")
@click.argument("text", required=False, default=None)
@click.option("--file", "input_file", default=None, type=click.Path(exists=True))
@click.option("--schedule", default=None)
@click.option("--plan", default=None)
@click.option("--tag", "tags", multiple=True)
@click.option("--title", default=None)
@click.option("--share/--unshare", "share_flag", default=None)
@click.option("--scratchpad", default=None)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--media", default=None)
@click.option("--append", "append_posts", is_flag=True,
              help="Append posts to existing thread instead of replacing")
@click.option("--platform", default=None, help="Comma-separated target platforms")
@click.option("--content-markdown", default=None, help="X Article markdown")
@click.option("--cover-media-id", default=None, help="X Article cover media ID")
@click.option("--paid-partnership", is_flag=True)
@click.option("--made-with-ai", is_flag=True)
@click.option("--hide-link-preview", is_flag=True)
@click.option(
    "--qrt", "--quote-post-url", "qrt", default=None,
    help="Quote URL for X, Threads, Bluesky, Mastodon, or Substack",
)
@click.option("--community", default=None, help="X community ID")
@click.option("--force-overwrite-comments", is_flag=True)
@click.option("--exclude-comment-markers", is_flag=True)
@_platform_field_options
@shared_options
@error_handler
def update(
    draft_id, text, input_file, schedule, plan, tags, title, share_flag, scratchpad,
    auto_retweet, auto_plug, media, append_posts, platform, content_markdown, cover_media_id,
    paid_partnership, made_with_ai, hide_link_preview, force_overwrite_comments,
    exclude_comment_markers, qrt, community,
    reply_settings, subscribers_only, share_with_followers,
    linkedin_first_comment, linkedin_reshare_target,
    api_key, account, use_text, use_json, quiet, debug,
):
    """Update an existing draft. Text supports === for thread post splitting."""
    platform_fields = dict(
        reply_settings=reply_settings, subscribers_only=subscribers_only,
        share_with_followers=share_with_followers,
        linkedin_first_comment=linkedin_first_comment,
        linkedin_reshare_target=linkedin_reshare_target,
    )

    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    if input_file:
        with open(input_file, encoding="utf-8") as fh:
            text = fh.read().strip()
    if schedule and plan:
        raise TypefullyError("--schedule and --plan are mutually exclusive", code="invalid_input")
    schedule = _apply_timezone(schedule, cfg)
    plan = _apply_timezone(plan, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload: dict[str, Any] = {}

        if content_markdown is not None or cover_media_id is not None:
            target_platforms = _resolve_platforms(client, ssid, platform)
            _validate_platform_fields(target_platforms, platform_fields)
            if community is not None:
                raise TypefullyError("--community requires X posts", code="invalid_input")
            if target_platforms != ["x_article"]:
                raise TypefullyError(
                    "X Article updates require --platform x_article", code="invalid_input"
                )
            article: dict[str, Any] = {}
            if content_markdown is not None:
                article["content_markdown"] = content_markdown
            if cover_media_id is not None:
                article["cover_media_id"] = None if cover_media_id == "null" else cover_media_id
            payload["platforms"] = {"x_article": article}
        elif text:
            if append_posts:
                # Fetch existing draft to get current posts
                existing = client.get_draft(ssid, draft_id)
                target_platforms = _resolve_platforms(client, ssid, platform)
                new_parts = [p.strip() for p in text.split("===") if p.strip()]
                additions = _build_draft_payload(
                    posts_text=new_parts, media=media, platforms=target_platforms,
                    quote_post_url=qrt,
                    paid_partnership=paid_partnership, made_with_ai=made_with_ai,
                    hide_link_preview=hide_link_preview,
                )["platforms"]
                for name, config in additions.items():
                    old = existing.get("platforms", {}).get(name, {})
                    old_posts = _editable_posts(name, old.get("posts", []))
                    if name == "substack" and old_posts:
                        raise TypefullyError(
                            "Substack Notes supports one post per draft; cannot append",
                            code="invalid_input",
                        )
                    if old.get("settings"):
                        config["settings"] = dict(old["settings"])
                    if name == "x" and community is not None:
                        config.setdefault("settings", {})["community_id"] = community
                    # Apply per-post options only to newly appended posts.
                    selected_fields = {
                        key: value for key, value in platform_fields.items()
                        if (name == "x" and key in {
                            "reply_settings", "subscribers_only", "share_with_followers"
                        }) or (name == "linkedin" and key.startswith("linkedin_"))
                    }
                    _apply_platform_fields({name: config}, selected_fields)
                    config["posts"] = old_posts + config["posts"]
                _validate_platform_fields(target_platforms, platform_fields)
                if community is not None and "x" not in target_platforms:
                    raise TypefullyError("--community requires X", code="invalid_input")
                payload["platforms"] = additions
            else:
                parts = [p.strip() for p in text.split("===") if p.strip()]
                target_platforms = _resolve_platforms(client, ssid, platform)
                payload["platforms"] = _build_draft_payload(
                    posts_text=parts, media=media, platforms=target_platforms,
                    quote_post_url=qrt,
                    paid_partnership=paid_partnership, made_with_ai=made_with_ai,
                    hide_link_preview=hide_link_preview, community=community, **platform_fields,
                )["platforms"]
        elif media or qrt or paid_partnership or made_with_ai or hide_link_preview or (
            community is not None or any(value is not None for value in platform_fields.values())
        ):
            existing = client.get_draft(ssid, draft_id)
            existing_platforms = existing.get("platforms", {})
            target_platforms = _resolve_platforms(client, ssid, platform) if platform else [
                name for name, config in existing_platforms.items()
                if name in POST_PLATFORMS and isinstance(config, dict) and config.get("enabled")
            ]
            if media and not platform and not (
                qrt or paid_partnership or made_with_ai or hide_link_preview
                or community is not None
                or any(value is not None for value in platform_fields.values())
            ):
                # Preserve the historical default for media-only updates (X).
                target_platforms = ["x"]
            _validate_platform_fields(target_platforms, platform_fields)
            x_options = community is not None or paid_partnership or made_with_ai or any(
                platform_fields[key] is not None
                for key in ("reply_settings", "subscribers_only", "share_with_followers")
            )
            li_options = any(platform_fields[key] is not None for key in (
                "linkedin_first_comment", "linkedin_reshare_target"
            ))
            if x_options and "x" not in target_platforms:
                raise TypefullyError("X-only options require X", code="invalid_input")
            if hide_link_preview and not set(target_platforms) & LINK_PREVIEW_PLATFORMS:
                raise TypefullyError("Link-preview hiding requires a supported platform",
                                    code="invalid_input")
            quote_platform = _quote_platform(qrt, target_platforms) if qrt else None
            payload["platforms"] = {}
            for name in target_platforms:
                if not (
                    name == quote_platform or (name == "x" and x_options)
                    or (name == "linkedin" and li_options)
                    or (name in LINK_PREVIEW_PLATFORMS and hide_link_preview)
                    or (media and (not qrt or name == quote_platform))
                ):
                    continue
                source = existing_platforms.get(name, {})
                posts = _editable_posts(name, source.get("posts", []))
                if not posts:
                    raise TypefullyError(
                        f"Cannot update {name}: draft has no existing posts", code="invalid_input"
                    )
                if name == quote_platform:
                    for post in posts if name == "x" else posts[:1]:
                        post["quote_post_url"] = qrt
                if media and (not qrt or name == quote_platform):
                    posts[0]["media_ids"] = [m.strip() for m in media.split(",") if m.strip()]
                if name == "x":
                    for post in posts:
                        if paid_partnership:
                            post["paid_partnership"] = True
                        if made_with_ai:
                            post["made_with_ai"] = True
                if name in LINK_PREVIEW_PLATFORMS and hide_link_preview:
                    for post in posts:
                        post["hide_link_preview"] = True
                config = {"enabled": True, "posts": posts}
                if source.get("settings"):
                    config["settings"] = dict(source["settings"])
                if name == "x" and community is not None:
                    config.setdefault("settings", {})["community_id"] = community
                payload["platforms"][name] = config
            _apply_platform_fields(payload["platforms"], platform_fields)
            if not payload["platforms"]:
                raise TypefullyError("Draft has no editable post platforms", code="invalid_input")

        if share_flag is True:
            payload["share"] = True
        elif share_flag is False:
            payload["share"] = False

        if scratchpad is not None:
            payload["scratchpad_text"] = scratchpad
        if auto_retweet is True:
            payload["auto_retweet_enabled"] = True
        elif auto_retweet is False:
            payload["auto_retweet_enabled"] = False
        if auto_plug is True:
            payload["auto_plug_enabled"] = True
        elif auto_plug is False:
            payload["auto_plug_enabled"] = False

        if schedule == "next":
            payload["publish_at"] = "next-free-slot"
        elif schedule == "now":
            payload["publish_at"] = "now"
        elif schedule:
            payload["publish_at"] = schedule
        if plan == "next":
            payload["plan_at"] = "next-free-slot"
        elif plan == "null":
            payload["plan_at"] = None
        elif plan:
            payload["plan_at"] = plan

        if tags:
            payload["tags"] = list(tags)
        if title:
            payload["draft_title"] = title
        if force_overwrite_comments:
            payload["force_overwrite_comments"] = True
        if not payload:
            raise TypefullyError("No update fields provided", code="invalid_input")

        console.status(f"Updating draft {draft_id}...")
        data = client.update_draft(
            ssid, draft_id, payload, exclude_comment_markers=exclude_comment_markers
        )
        _output(data, use_text, fmt.print_draft_short)


# --- delete ---


@cli.command()
@click.argument("ids", nargs=-1, required=True)
@shared_options
@error_handler
def delete(ids, api_key, account, use_text, use_json, quiet, debug):
    """Delete one or more drafts."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        deleted: list[str] = []
        errors: list[dict] = []
        for i, draft_id in enumerate(ids):
            if i > 0:
                client.rate_delay()
            console.status(f"Deleting {draft_id}...")
            try:
                client.delete_draft(ssid, draft_id)
                deleted.append(draft_id)
            except TypefullyError as e:
                msg = e.user_message if isinstance(e, APIError) else str(e)
                errors.append({"id": draft_id, "message": msg})

        result = {"deleted": deleted, "errors": errors}
        _handle_multi_result(
            result, errors, deleted, len(ids),
            use_text, fmt.print_delete_result, console,
        )


# --- drafts ---


@cli.command()
@click.option("--status", "draft_status", default=None, help="Filter: draft|planned|scheduled|publishing|published|error")
@click.option("-n", "--limit", default=10, type=int)
@click.option("--offset", default=0, type=click.IntRange(min=0))
@click.option("--order", default="-updated_at")
@click.option("--tag", multiple=True, help="Filter by tag slug (repeat for multiple tags)")
@click.option("--content-filter", default=None, help="Filter: original|repost")
@shared_options
@error_handler
def drafts(draft_status, limit, offset, order, tag, content_filter, api_key, account, use_text, use_json, quiet, debug):
    """List drafts with optional filters."""
    _validate_limit(limit)
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "order_by": order,
        }
        if draft_status:
            params["status"] = draft_status
        if tag:
            params["tag"] = tag[0] if len(tag) == 1 else list(tag)
        if content_filter:
            params["content_filter"] = content_filter

        data = client.list_drafts(ssid, **params)
        _output(data, use_text, fmt.print_drafts_list)


# --- tags ---


@cli.command()
@click.option("-n", "--limit", default=50, type=int)
@click.option("--offset", default=0, type=click.IntRange(min=0))
@shared_options
@error_handler
def tags(limit, offset, api_key, account, use_text, use_json, quiet, debug):
    """List tags."""
    _validate_limit(limit)
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.list_tags(ssid, limit=limit, offset=offset)
        results = data.get("results", [])
        if use_text:
            fmt.print_tags(results)
        else:
            write_success(results)


# --- tag-create ---


@cli.command("tag-create")
@click.argument("name")
@shared_options
@error_handler
def tag_create(name, api_key, account, use_text, use_json, quiet, debug):
    """Create a tag."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.create_tag(ssid, name)
        if use_text:
            fmt.print_tags([data])
        else:
            write_success(data)


# --- upload ---


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--no-wait", is_flag=True, help="Return immediately after S3 upload, skip processing poll")
@click.option("--timeout", "poll_timeout", default=60, type=int,
              help="Media processing poll timeout in seconds")
@click.option("--alt-text", default=None, help="Media alt text (max 1000 characters)")
@shared_options
@error_handler
def upload(file_path, no_wait, poll_timeout, alt_text, api_key, account, use_text, use_json, quiet, debug):
    """Upload a media file and return its media ID."""
    if alt_text is not None and len(alt_text) > 1000:
        raise TypefullyError("--alt-text must be at most 1000 characters", code="invalid_input")
    upload_options = {"alt_text": alt_text} if alt_text is not None else {}
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        if no_wait:
            from typefully_cli.media import _sanitize_filename
            file_name = _sanitize_filename(os.path.basename(file_path))
            console.status(f"Requesting upload URL for {file_name}...")
            upload_response = client.request_upload(ssid, file_name, **upload_options)
            media_id = upload_response.get("media_id", "")
            upload_url = upload_response.get("upload_url", "")
            console.status(f"Uploading {file_name}...")
            client.upload_to_s3(upload_url, file_path)
            data = {"media_id": media_id, "status": "uploading"}
            _output(data, use_text, fmt.print_upload_result)
        else:
            data = upload_media(client, ssid, file_path, console, timeout=poll_timeout, **upload_options)
            _output(data, use_text, fmt.print_upload_result)


# --- batch ---


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--schedule", default=None, help="Default schedule for all drafts")
@click.option("--tag", "tags", multiple=True, help="Default tag (repeatable)")
@click.option("--share/--no-share", default=False)
@click.option("--dry-run", is_flag=True)
@click.option("--output", "output_file", default=None, type=click.Path(), help="JSON results log")
@shared_options
@error_handler
def batch(file_path, schedule, tags, share, dry_run, output_file, api_key, account, use_text, use_json, quiet, debug):
    """Batch create drafts from a text file.

    File format: drafts separated by --- on its own line.
    Thread posts separated by === on its own line.
    Optional metadata at top of each block: schedule:, tag:, title:, scratchpad:, media:

    Example:

        tag: launch
        schedule: next
        First tweet in a thread
        ===
        Second tweet
        ---
        A standalone tweet
    """
    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    entries = parse_batch_file(content)
    merge_defaults(entries, default_schedule=schedule, default_tags=tags)

    # Resolve text mode early (dry_run path doesn't call _get_client_and_console)
    cfg_for_mode = Config.load()
    use_text = _resolve_text_mode(use_text, use_json, cfg_for_mode)

    if dry_run:
        result = {"dry_run": True, "entries": [e.to_dict() for e in entries]}
        if use_text:
            fmt.print_batch_dry_run([e.to_dict() for e in entries])
        else:
            write_success(result)
        return

    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        # Tag preflight
        all_tags = set()
        for e in entries:
            all_tags.update(e.tags)
        if all_tags:
            for w in client.ensure_tags(ssid, list(all_tags)):
                console.warning(w)

        created: list[dict] = []
        errors: list[dict] = []

        for i, entry in enumerate(entries):
            if i > 0:
                client.rate_delay()

            payload = _build_draft_payload(
                posts_text=entry.posts,
                schedule=entry.schedule,
                tags=entry.tags,
                title=entry.title,
                media=",".join(entry.media_ids) if entry.media_ids else None,
                share=share,
                scratchpad=entry.scratchpad,
            )

            label = "thread" if len(entry.posts) > 1 else "single"
            console.status(f"[{i+1}/{len(entries)}] Creating {label}...")

            try:
                data = client.create_draft(ssid, payload)
                created.append({
                    "id": data.get("id"),
                    "type": label,
                    "posts": len(entry.posts),
                    "share_url": data.get("share_url", ""),
                })
            except TypefullyError as e:
                msg = e.user_message if isinstance(e, APIError) else str(e)
                errors.append({
                    "index": i,
                    "message": msg,
                    "preview": entry.posts[0][:50] if entry.posts else "",
                })

        result = {"total": len(entries), "created": created, "errors": errors}

        if output_file:
            with open(output_file, "w") as f:
                json.dump(result, f, indent=2)
            console.status(f"Results written to {output_file}")

        _handle_multi_result(
            result, errors, created, len(entries),
            use_text, fmt.print_batch_result, console,
        )


# --- analytics ---


@cli.command()
@click.option("--platform", default="x", help="Platform: x (default)")
@click.option("--start-date", default="", help="Start date YYYY-MM-DD")
@click.option("--end-date", default="", help="End date YYYY-MM-DD")
@click.option("--include-replies", is_flag=True, help="Include reply posts")
@click.option("-n", "--limit", default=50, type=int, help="Number of posts (max: 50)")
@click.option("--offset", default=0, type=click.IntRange(min=0))
@shared_options
@error_handler
def analytics(platform, start_date, end_date, include_replies, limit, offset,
              api_key, account, use_text, use_json, quiet, debug):
    """List post analytics (impressions, engagement)."""
    _validate_limit(limit)
    start_date = _validate_date(start_date, "--start-date")
    end_date = _validate_date(end_date, "--end-date")
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.list_analytics(
            ssid, platform=platform, start_date=start_date, end_date=end_date,
            include_replies=include_replies, limit=limit, offset=offset,
        )
        _output(data, use_text, fmt.print_analytics)


@cli.command("followers")
@click.option("--platform", default="x", help="Platform: x (default)")
@click.option("--start-date", default="", help="Start date YYYY-MM-DD")
@click.option("--end-date", default="", help="End date YYYY-MM-DD")
@shared_options
@error_handler
def followers(platform, start_date, end_date, api_key, account, use_text, use_json, quiet, debug):
    """Show follower analytics for a platform."""
    start_date = _validate_date(start_date, "--start-date")
    end_date = _validate_date(end_date, "--end-date")
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_follower_analytics(
            ssid, platform=platform, start_date=start_date, end_date=end_date
        )
        _output(data, use_text)


# --- queue ---


@cli.command()
@click.option("--start-date", default="", help="Start date YYYY-MM-DD")
@click.option("--end-date", default="", help="End date YYYY-MM-DD")
@shared_options
@error_handler
def queue(start_date, end_date, api_key, account, use_text, use_json, quiet, debug):
    """View the posting queue (scheduled slots and drafts)."""
    start_date = _validate_date(start_date, "--start-date")
    end_date = _validate_date(end_date, "--end-date")
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_queue(ssid, start_date=start_date, end_date=end_date)
        _output(data, use_text, fmt.print_queue)


# --- queue-schedule ---


@cli.command("queue-schedule")
@click.argument("action", type=click.Choice(["get", "set"]))
@click.option("--rules", default=None, help="JSON array of schedule rules (for set)")
@shared_options
@error_handler
def queue_schedule(action, rules, api_key, account, use_text, use_json, quiet, debug):
    """Get or set queue schedule rules.

    GET: view current posting times.
    SET: replace schedule rules. Rules format: [{"h":9,"m":30,"days":["mon","wed","fri"]}]
    """
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        if action == "get":
            data = client.get_queue_schedule(ssid)
            _output(data, use_text, fmt.print_queue_schedule)
        else:
            if not rules:
                raise TypefullyError(
                    "Missing --rules for set action",
                    code="invalid_input",
                    hint='Example: --rules \'[{"h":9,"m":30,"days":["mon","wed","fri"]}]\'',
                )
            try:
                parsed = json.loads(rules)
            except json.JSONDecodeError:
                raise TypefullyError(
                    "Invalid JSON in --rules",
                    code="invalid_input",
                    hint="Rules must be a valid JSON array",
                )
            data = client.set_queue_schedule(ssid, parsed)
            _output(data, use_text, fmt.print_queue_schedule)


# --- linkedin-resolve ---


@cli.command("linkedin-resolve")
@click.argument("url")
@shared_options
@error_handler
def linkedin_resolve(url, api_key, account, use_text, use_json, quiet, debug):
    """Resolve a LinkedIn company URL to mention syntax."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.resolve_linkedin_org(ssid, url)
        _output(data, use_text, fmt.print_linkedin_resolve)


# --- comments ---


@cli.group()
def comments():
    """Manage review comment threads on a draft."""


@comments.command("list")
@click.argument("draft_id")
@click.option("--platform", default=None)
@click.option("--status", "comment_status", default="unresolved")
@click.option("-n", "--limit", default=10, type=int)
@click.option("--offset", default=0, type=click.IntRange(min=0))
@shared_options
@error_handler
def comments_list(draft_id, platform, comment_status, limit, offset,
                  api_key, account, use_text, use_json, quiet, debug):
    """List comment threads for a draft."""
    _validate_limit(limit)
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if platform:
            params["platform"] = platform
        if comment_status:
            params["status"] = comment_status
        _output(client.list_comment_threads(ssid, draft_id, **params), use_text)


@comments.command("create")
@click.argument("draft_id")
@click.option("--selected-text", required=True)
@click.option("--text", "comment_text", required=True)
@click.option("--post-index", type=int, default=None)
@click.option("--occurrence", type=int, default=None)
@click.option("--platform", default=None)
@shared_options
@error_handler
def comments_create(draft_id, selected_text, comment_text, post_index, occurrence, platform,
                    api_key, account, use_text, use_json, quiet, debug):
    """Create a review comment anchored to draft text."""
    if platform == "x_article":
        if post_index not in (None, 0):
            raise TypefullyError("--post-index must be 0 for x_article", code="invalid_input")
    elif post_index is None or post_index < 0:
        raise TypefullyError("--post-index must be a non-negative integer", code="invalid_input")
    if occurrence is not None and occurrence < 0:
        raise TypefullyError("--occurrence must be a non-negative integer", code="invalid_input")
    payload: dict[str, Any] = {"selected_text": selected_text, "text": comment_text}
    if platform:
        payload["platform"] = platform
    if platform != "x_article":
        payload["post_index"] = post_index
    if occurrence is not None:
        payload["occurrence"] = occurrence
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        _output(client.create_comment_thread(ssid, draft_id, payload), use_text)


@comments.command("reply")
@click.argument("draft_id")
@click.argument("thread_id")
@click.option("--text", "comment_text", required=True)
@shared_options
@error_handler
def comments_reply(draft_id, thread_id, comment_text, api_key, account, use_text, use_json, quiet, debug):
    """Reply to a review comment thread."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        _output(client.reply_to_comment_thread(ssid, draft_id, thread_id, comment_text), use_text)


@comments.command("resolve")
@click.argument("draft_id")
@click.argument("thread_id")
@shared_options
@error_handler
def comments_resolve(draft_id, thread_id, api_key, account, use_text, use_json, quiet, debug):
    """Resolve a review comment thread."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        _output(client.resolve_comment_thread(ssid, draft_id, thread_id), use_text)


@comments.command("update")
@click.argument("draft_id")
@click.argument("thread_id")
@click.argument("comment_id")
@click.option("--text", "comment_text", required=True)
@shared_options
@error_handler
def comments_update(draft_id, thread_id, comment_id, comment_text,
                    api_key, account, use_text, use_json, quiet, debug):
    """Update a comment written by current user."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        _output(client.update_comment(ssid, draft_id, thread_id, comment_id, comment_text), use_text)


@comments.command("delete")
@click.argument("draft_id")
@click.argument("thread_id")
@click.argument("comment_id", required=False)
@shared_options
@error_handler
def comments_delete(draft_id, thread_id, comment_id, api_key, account, use_text, use_json, quiet, debug):
    """Delete a comment, or entire comment thread when comment ID is omitted."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        if comment_id:
            client.delete_comment(ssid, draft_id, thread_id, comment_id)
        else:
            client.delete_comment_thread(ssid, draft_id, thread_id)
        _output({"deleted": comment_id or thread_id, "type": "comment" if comment_id else "thread"}, use_text)


# --- publish ---


@cli.command()
@click.argument("draft_id")
@shared_options
@error_handler
def publish(draft_id, api_key, account, use_text, use_json, quiet, debug):
    """Publish a draft immediately."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        console.status(f"Publishing draft {draft_id}...")
        data = client.update_draft(ssid, draft_id, {"publish_at": "now"})
        _output(data, use_text, fmt.print_draft_short)


# --- schedule ---


@cli.command("schedule")
@click.argument("draft_id")
@click.option("--time", "schedule_time", default="next",
              help="ISO datetime or 'next' (default: next)")
@shared_options
@error_handler
def schedule_cmd(draft_id, schedule_time, api_key, account, use_text, use_json, quiet, debug):
    """Schedule a draft. Defaults to next free slot."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    schedule_time = _apply_timezone(schedule_time, cfg) or schedule_time
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        publish_at = "next-free-slot" if schedule_time == "next" else schedule_time
        console.status(f"Scheduling draft {draft_id}...")
        data = client.update_draft(ssid, draft_id, {"publish_at": publish_at})
        _output(data, use_text, fmt.print_draft_short)


@cli.command("plan")
@click.argument("draft_id")
@click.option("--time", "plan_time", required=True, help="ISO datetime or 'next'")
@shared_options
@error_handler
def plan_cmd(draft_id, plan_time, api_key, account, use_text, use_json, quiet, debug):
    """Place a draft on calendar without scheduling publication."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    plan_time = _apply_timezone(plan_time, cfg) or plan_time
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        plan_at = "next-free-slot" if plan_time == "next" else plan_time
        console.status(f"Planning draft {draft_id}...")
        data = client.update_draft(ssid, draft_id, {"plan_at": plan_at})
        _output(data, use_text, fmt.print_draft_short)


# --- media-status ---


@cli.command("media-status")
@click.argument("media_id")
@shared_options
@error_handler
def media_status(media_id, api_key, account, use_text, use_json, quiet, debug):
    """Check the processing status of an uploaded media file."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    use_text = _resolve_text_mode(use_text, use_json, cfg)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_media(ssid, media_id)
        _output(data, use_text, fmt.print_media_status)


# --- Payload builder ---


def _build_draft_payload(
    posts_text: list[str],
    schedule: str | None = None,
    plan: str | None = None,
    tags: list[str] | None = None,
    title: str | None = None,
    media: str | None = None,
    share: bool = False,
    reply_to: str | None = None,
    scratchpad: str | None = None,
    threadify: bool = False,
    auto_retweet: bool | None = None,
    auto_plug: bool | None = None,
    quote_post_url: str | None = None,
    community: str | None = None,
    platforms: list[str] | None = None,
    content_markdown: str | None = None,
    cover_media_id: str | None = None,
    paid_partnership: bool = False,
    made_with_ai: bool = False,
    hide_link_preview: bool = False,
    reply_settings: str | None = None,
    subscribers_only: bool | None = None,
    share_with_followers: bool | None = None,
    linkedin_first_comment: str | None = None,
    linkedin_reshare_target: str | None = None,
) -> dict:
    """Build a draft creation payload from CLI args."""
    target_platforms = platforms or ["x"]
    quote_platform = _quote_platform(quote_post_url, target_platforms) if quote_post_url else None
    if "x_article" in target_platforms:
        if len(target_platforms) != 1 or not content_markdown or posts_text:
            raise TypefullyError(
                "x_article requires only --platform x_article and --content-markdown",
                code="invalid_input",
            )
        article: dict[str, Any] = {"content_markdown": content_markdown}
        if cover_media_id is not None:
            article["cover_media_id"] = None if cover_media_id == "null" else cover_media_id
        platform_payload: dict[str, Any] = {"x_article": article}
    else:
        if content_markdown or cover_media_id is not None:
            raise TypefullyError(
                "--content-markdown and --cover-media-id require --platform x_article",
                code="invalid_input",
            )
        if not posts_text:
            raise TypefullyError("No text provided", code="invalid_input")
        if "substack" in target_platforms and len(posts_text) > 1:
            raise TypefullyError(
                "Substack Notes supports one post per draft; threads are not supported",
                code="invalid_input",
            )
        if (paid_partnership or made_with_ai or reply_to or community) and "x" not in target_platforms:
            raise TypefullyError("X-only options require x in --platform", code="invalid_input")
        if hide_link_preview and not (set(target_platforms) & LINK_PREVIEW_PLATFORMS):
            raise TypefullyError(
                "--hide-link-preview requires LinkedIn, Threads, or Substack",
                code="invalid_input",
            )

        base_posts = [{"text": t} for t in posts_text]
        if media:
            base_posts[0]["media_ids"] = [m.strip() for m in media.split(",")]
        platform_payload = {}
        for name in target_platforms:
            posts = [dict(post) for post in base_posts]
            if name == quote_platform:
                # Keep legacy X thread behavior; new quote platforms quote the first post.
                for post in posts if name == "x" else posts[:1]:
                    post["quote_post_url"] = quote_post_url
            if name == "x":
                for post in posts:
                    if paid_partnership:
                        post["paid_partnership"] = True
                    if made_with_ai:
                        post["made_with_ai"] = True
            if name in LINK_PREVIEW_PLATFORMS and hide_link_preview:
                for post in posts:
                    post["hide_link_preview"] = True
            config: dict[str, Any] = {"enabled": True, "posts": posts}
            if name == "x" and (reply_to or community):
                config["settings"] = {}
                if reply_to:
                    config["settings"]["reply_to_url"] = reply_to
                if community:
                    config["settings"]["community_id"] = community
            platform_payload[name] = config

    _apply_platform_fields(platform_payload, dict(
        reply_settings=reply_settings, subscribers_only=subscribers_only,
        share_with_followers=share_with_followers,
        linkedin_first_comment=linkedin_first_comment,
        linkedin_reshare_target=linkedin_reshare_target,
    ))
    payload: dict[str, Any] = {"platforms": platform_payload}

    if threadify:
        payload["threadify"] = True
    if share:
        payload["share"] = True
    if scratchpad:
        payload["scratchpad_text"] = scratchpad
    if auto_retweet is True:
        payload["auto_retweet_enabled"] = True
    elif auto_retweet is False:
        payload["auto_retweet_enabled"] = False
    if auto_plug is True:
        payload["auto_plug_enabled"] = True
    elif auto_plug is False:
        payload["auto_plug_enabled"] = False

    if schedule == "next":
        payload["publish_at"] = "next-free-slot"
    elif schedule == "now":
        payload["publish_at"] = "now"
    elif schedule:
        payload["publish_at"] = schedule
    if plan == "next":
        payload["plan_at"] = "next-free-slot"
    elif plan:
        payload["plan_at"] = plan

    if tags:
        payload["tags"] = tags
    if title:
        payload["draft_title"] = title

    return payload


# Register advanced, explicit request-input and media metadata commands.
from typefully_cli.payloads import register_commands  # noqa: E402

register_commands(cli)
