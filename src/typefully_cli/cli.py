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


# --- Shared option decorator ---


def shared_options(f):
    """Add --api-key, --account, --text, --quiet, --debug to a subcommand."""

    @click.option("--api-key", default=None, help="API key (overrides env/config)")
    @click.option(
        "--account", "-a", default=None, help="Account name, username, or numeric ID"
    )
    @click.option("--text", "use_text", is_flag=True, help="Human-readable Rich output")
    @click.option("--quiet", "-q", is_flag=True, help="Suppress non-error stderr")
    @click.option("--debug", is_flag=True, hidden=True, help="Log HTTP requests to stderr")
    @wraps(f)
    def wrapper(*args, **kwargs):
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


@cli.group()
def config():
    """Manage configuration (~/.config/typefully/config.toml)."""


@config.command("set")
@click.argument("key")
@click.argument("value")
@error_handler
def config_set_cmd(key: str, value: str, **kwargs):
    """Set a config value. Keys: api_key, default_account, onepassword_item."""
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
def me(api_key, account, use_text, quiet, debug):
    """Show current authenticated user."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        data = client.me()
        _output(data, use_text, fmt.print_user)


# --- accounts ---


@cli.command()
@shared_options
@error_handler
def accounts(api_key, account, use_text, quiet, debug):
    """List connected social sets."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
def account_detail(name, api_key, account, use_text, quiet, debug):
    """Show details for an account. NAME is optional (falls back to --account or config default)."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
def recent(limit, since, until_date, output_format, api_key, account, use_text, quiet, debug):
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
@click.argument("text")
@click.option("--schedule", default=None, help="ISO datetime, 'next', or 'now'")
@click.option("--tag", "tags", multiple=True, help="Tag name (repeatable, auto-created)")
@click.option("--title", default=None)
@click.option("--media", default=None, help="Comma-separated media IDs")
@click.option("--share/--no-share", default=False)
@click.option("--reply-to", default=None, help="URL of tweet to reply to")
@click.option("--scratchpad", default=None, help="Internal notes (not published)")
@click.option("--qrt", default=None, help="Quote-retweet URL")
@click.option("--threadify/--no-threadify", default=False)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--linkedin", is_flag=True)
@click.option("--threads", is_flag=True)
@click.option("--bluesky", is_flag=True)
@click.option("--mastodon", is_flag=True)
@shared_options
@error_handler
def draft(
    text, schedule, tags, title, media, share, reply_to, scratchpad,
    qrt, threadify, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon,
    api_key, account, use_text, quiet, debug,
):
    """Create a draft post."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        # QRT: append URL
        if qrt:
            text = f"{text}\n{qrt}"

        # Tag auto-creation
        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload = _build_draft_payload(
            posts_text=[text], schedule=schedule, tags=list(tags),
            title=title, media=media, share=share, reply_to=reply_to,
            scratchpad=scratchpad, threadify=threadify,
            auto_retweet=auto_retweet, auto_plug=auto_plug,
            linkedin=linkedin, threads_flag=threads, bluesky=bluesky, mastodon=mastodon,
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
@click.option("--qrt", default=None)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--linkedin", is_flag=True)
@click.option("--threads", is_flag=True)
@click.option("--bluesky", is_flag=True)
@click.option("--mastodon", is_flag=True)
@shared_options
@error_handler
def thread(
    posts, schedule, tags, title, media, share, reply_to, scratchpad,
    qrt, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon,
    api_key, account, use_text, quiet, debug,
):
    """Create a multi-post thread. Provide 2+ posts as separate arguments."""
    if len(posts) < 2:
        Console(quiet).error_json({
            "code": "invalid_input",
            "message": "Thread requires at least 2 posts",
            "hint": 'Usage: typefully thread "post 1" "post 2" [...]',
        })
        sys.exit(1)

    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        posts_list = list(posts)
        if qrt and posts_list:
            posts_list[0] = f"{posts_list[0]}\n{qrt}"

        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload = _build_draft_payload(
            posts_text=posts_list, schedule=schedule, tags=list(tags),
            title=title, media=media, share=share, reply_to=reply_to,
            scratchpad=scratchpad, threadify=False,
            auto_retweet=auto_retweet, auto_plug=auto_plug,
            linkedin=linkedin, threads_flag=threads, bluesky=bluesky, mastodon=mastodon,
        )

        console.status(f"Creating {len(posts_list)}-post thread...")
        data = client.create_draft(ssid, payload)
        _output(data, use_text, fmt.print_draft_short)


# --- get ---


@cli.command()
@click.argument("draft_id")
@shared_options
@error_handler
def get(draft_id, api_key, account, use_text, quiet, debug):
    """View a specific draft."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = client.get_draft(ssid, draft_id)
        _output(data, use_text, fmt.print_draft)


# --- open ---


@cli.command("open")
@click.argument("draft_id")
@shared_options
@error_handler
def open_draft(draft_id, api_key, account, use_text, quiet, debug):
    """Open a draft in the browser."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
@click.option("--schedule", default=None)
@click.option("--tag", "tags", multiple=True)
@click.option("--title", default=None)
@click.option("--share/--unshare", "share_flag", default=None)
@click.option("--scratchpad", default=None)
@click.option("--auto-retweet/--no-auto-retweet", default=None)
@click.option("--auto-plug/--no-auto-plug", default=None)
@click.option("--media", default=None)
@shared_options
@error_handler
def update(
    draft_id, text, schedule, tags, title, share_flag, scratchpad,
    auto_retweet, auto_plug, media,
    api_key, account, use_text, quiet, debug,
):
    """Update an existing draft. Text supports === for thread post splitting."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)

        if tags:
            for w in client.ensure_tags(ssid, list(tags)):
                console.warning(w)

        payload: dict[str, Any] = {}

        if text:
            parts = [p.strip() for p in text.split("===") if p.strip()]
            posts = [{"text": p} for p in parts]
            if media:
                posts[0]["media_ids"] = [m.strip() for m in media.split(",")]
            payload["platforms"] = {"x": {"enabled": True, "posts": posts}}
        elif media:
            payload["platforms"] = {
                "x": {"enabled": True, "posts": [{"media_ids": [m.strip() for m in media.split(",")]}]}
            }

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

        if tags:
            payload["tags"] = list(tags)
        if title:
            payload["draft_title"] = title

        console.status(f"Updating draft {draft_id}...")
        data = client.update_draft(ssid, draft_id, payload)
        _output(data, use_text, fmt.print_draft_short)


# --- delete ---


@cli.command()
@click.argument("ids", nargs=-1, required=True)
@shared_options
@error_handler
def delete(ids, api_key, account, use_text, quiet, debug):
    """Delete one or more drafts."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
@click.option("--status", "draft_status", default=None, help="Filter: draft|published|scheduled|error")
@click.option("-n", "--limit", default=10, type=int)
@click.option("--offset", default=0, type=int)
@click.option("--order", default="-updated_at")
@click.option("--tag", default=None, help="Filter by tag slug")
@click.option("--content-filter", default=None, help="Filter: original|repost")
@shared_options
@error_handler
def drafts(draft_status, limit, offset, order, tag, content_filter, api_key, account, use_text, quiet, debug):
    """List drafts with optional filters."""
    _validate_limit(limit)
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
            params["tag"] = tag
        if content_filter:
            params["content_filter"] = content_filter

        data = client.list_drafts(ssid, **params)
        _output(data, use_text, fmt.print_drafts_list)


# --- tags ---


@cli.command()
@click.option("-n", "--limit", default=50, type=int)
@click.option("--offset", default=0, type=int)
@shared_options
@error_handler
def tags(limit, offset, api_key, account, use_text, quiet, debug):
    """List tags."""
    _validate_limit(limit)
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
def tag_create(name, api_key, account, use_text, quiet, debug):
    """Create a tag."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
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
@shared_options
@error_handler
def upload(file_path, api_key, account, use_text, quiet, debug):
    """Upload a media file and return its media ID."""
    client, console, cfg = _get_client_and_console(api_key, quiet, debug=debug)
    with client:
        ssid = _resolve_account_id(client, account, cfg)
        data = upload_media(client, ssid, file_path, console)
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
def batch(file_path, schedule, tags, share, dry_run, output_file, api_key, account, use_text, quiet, debug):
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


# --- Payload builder ---


def _build_draft_payload(
    posts_text: list[str],
    schedule: str | None = None,
    tags: list[str] | None = None,
    title: str | None = None,
    media: str | None = None,
    share: bool = False,
    reply_to: str | None = None,
    scratchpad: str | None = None,
    threadify: bool = False,
    auto_retweet: bool | None = None,
    auto_plug: bool | None = None,
    linkedin: bool = False,
    threads_flag: bool = False,
    bluesky: bool = False,
    mastodon: bool = False,
) -> dict:
    """Build a draft creation payload from CLI args."""
    posts = [{"text": t} for t in posts_text]

    if media:
        posts[0]["media_ids"] = [m.strip() for m in media.split(",")]

    x_platform: dict[str, Any] = {"enabled": True, "posts": posts}
    if reply_to:
        x_platform["settings"] = {"reply_to_url": reply_to}

    platforms: dict[str, Any] = {"x": x_platform}
    for flag, name in [(linkedin, "linkedin"), (threads_flag, "threads"), (bluesky, "bluesky"), (mastodon, "mastodon")]:
        if flag:
            platforms[name] = {"enabled": True, "posts": posts}

    payload: dict[str, Any] = {"platforms": platforms}

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

    if tags:
        payload["tags"] = tags
    if title:
        payload["draft_title"] = title

    return payload
