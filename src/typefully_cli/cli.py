"""Click CLI: all 17 commands with shared per-subcommand options."""

from __future__ import annotations

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
from typefully_cli.exceptions import TypefullyError
from typefully_cli.media import upload_media
from typefully_cli import output as fmt


# --- Shared option decorator ---


def shared_options(f):
    """Add --api-key, --account, --text, --quiet to a subcommand."""

    @click.option("--api-key", default=None, help="API key (overrides env/config)")
    @click.option(
        "--account", "-a", default=None, help="Account name, username, or numeric ID"
    )
    @click.option("--text", "use_text", is_flag=True, help="Human-readable Rich output")
    @click.option("--quiet", "-q", is_flag=True, help="Suppress non-error stderr")
    @wraps(f)
    def wrapper(*args, **kwargs):
        return f(*args, **kwargs)

    return wrapper


def _get_client_and_console(
    api_key: str | None, quiet: bool, config: Config | None = None
) -> tuple[TypefullyClient, Console, Config]:
    """Resolve auth and return client + console."""
    cfg = config or Config.load()
    console = Console(quiet=quiet)
    key = resolve_api_key(api_key, os.environ.get("TYPEFULLY_API_KEY"), cfg)
    client = TypefullyClient(api_key=key)
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
    if isinstance(err, TypefullyError) and err.code in ("auth_failed", "no_account"):
        sys.exit(1)
    sys.exit(2)


def _output(data: Any, use_text: bool, text_fn: Any = None) -> None:
    """Write JSON envelope to stdout, or call text_fn for --text mode."""
    if use_text and text_fn:
        text_fn(data)
    else:
        write_success(data)


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
def config_set_cmd(key: str, value: str):
    """Set a config value. Keys: api_key, default_account, onepassword_item."""
    try:
        cfg = Config.load()
        result = config_set(cfg, key, value)
        write_success(result)
    except Exception as e:
        Console().error_json({"code": "config_error", "message": str(e)})
        sys.exit(1)


@config.command("show")
def config_show_cmd():
    """Show current configuration (secrets redacted)."""
    cfg = Config.load()
    write_success(cfg.to_dict(redact=True))


@config.command("path")
def config_path_cmd():
    """Print the config file path."""
    cfg = Config.load()
    write_success({"path": str(cfg._path)})


# --- me ---


@cli.command()
@shared_options
def me(api_key, account, use_text, quiet):
    """Show current authenticated user."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            data = client.me()
            _output(data, use_text, fmt.print_user)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- accounts ---


@cli.command()
@shared_options
def accounts(api_key, account, use_text, quiet):
    """List connected social sets."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            sets = client.get_social_sets()
            if use_text:
                fmt.print_accounts(sets)
            else:
                write_success(sets)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- account-detail ---


@cli.command("account-detail")
@click.argument("name", required=False, default=None)
@shared_options
def account_detail(name, api_key, account, use_text, quiet):
    """Show details for an account. NAME is optional (falls back to --account or config default)."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg, positional=name)
            data = client.get_social_set(ssid)
            _output(data, use_text, fmt.print_account_detail)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- recent ---


@cli.command()
@click.option("-n", "--limit", default=3, type=int, help="Number of posts (default: 3)")
@click.option("--since", default="", help="Start date YYYY-MM-DD")
@click.option("--until", "until_date", default="", help="End date YYYY-MM-DD")
@shared_options
def recent(limit, since, until_date, api_key, account, use_text, quiet):
    """List recently published posts."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)
            posts = client.list_recent(ssid, limit=limit, since=since, until=until_date)
            if use_text:
                fmt.print_recent(posts)
            else:
                write_success(posts)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


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
def draft(
    text, schedule, tags, title, media, share, reply_to, scratchpad,
    qrt, threadify, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon,
    api_key, account, use_text, quiet,
):
    """Create a draft post."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
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
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


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
def thread(
    posts, schedule, tags, title, media, share, reply_to, scratchpad,
    qrt, auto_retweet, auto_plug,
    linkedin, threads, bluesky, mastodon,
    api_key, account, use_text, quiet,
):
    """Create a multi-post thread. Provide 2+ posts as separate arguments."""
    if len(posts) < 2:
        Console(quiet).error_json({
            "code": "invalid_input",
            "message": "Thread requires at least 2 posts",
            "hint": 'Usage: typefully thread "post 1" "post 2" [...]',
        })
        sys.exit(1)

    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
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
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- get ---


@cli.command()
@click.argument("draft_id")
@shared_options
def get(draft_id, api_key, account, use_text, quiet):
    """View a specific draft."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)
            data = client.get_draft(ssid, draft_id)
            _output(data, use_text, fmt.print_draft)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


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
def update(
    draft_id, text, schedule, tags, title, share_flag, scratchpad,
    auto_retweet, auto_plug, media,
    api_key, account, use_text, quiet,
):
    """Update an existing draft. Text supports === for thread post splitting."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)

            if tags:
                for w in client.ensure_tags(ssid, list(tags)):
                    console.warning(w)

            payload: dict[str, Any] = {}

            if text:
                # Split on === for thread support
                parts = [p.strip() for p in text.split("===") if p.strip()]
                posts = [{"text": p} for p in parts]
                if media:
                    posts[0]["media_ids"] = [m.strip() for m in media.split(",")]
                payload["platforms"] = {"x": {"enabled": True, "posts": posts}}
            elif media:
                # Media only update (no text change, add media to existing)
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
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- delete ---


@cli.command()
@click.argument("ids", nargs=-1, required=True)
@shared_options
def delete(ids, api_key, account, use_text, quiet):
    """Delete one or more drafts."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
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
                    errors.append({"id": draft_id, "message": str(e)})

            result = {"deleted": deleted, "errors": errors}
            if use_text:
                fmt.print_delete_result(result)
            else:
                write_success(result)

            if errors and not deleted:
                sys.exit(2)
            elif errors:
                sys.exit(3)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- drafts ---


@cli.command()
@click.option("--status", "draft_status", default=None, help="Filter: draft|published|scheduled|error")
@click.option("-n", "--limit", default=10, type=int)
@click.option("--offset", default=0, type=int)
@click.option("--order", default="-updated_at")
@click.option("--tag", default=None, help="Filter by tag slug")
@click.option("--content-filter", default=None, help="Filter: original|repost")
@shared_options
def drafts(draft_status, limit, offset, order, tag, content_filter, api_key, account, use_text, quiet):
    """List drafts with optional filters."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
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
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- tags ---


@cli.command()
@click.option("-n", "--limit", default=50, type=int)
@click.option("--offset", default=0, type=int)
@shared_options
def tags(limit, offset, api_key, account, use_text, quiet):
    """List tags."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)
            data = client.list_tags(ssid, limit=limit, offset=offset)
            results = data.get("results", [])
            if use_text:
                fmt.print_tags(results)
            else:
                write_success(results)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- tag-create ---


@cli.command("tag-create")
@click.argument("name")
@shared_options
def tag_create(name, api_key, account, use_text, quiet):
    """Create a tag."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)
            data = client.create_tag(ssid, name)
            if use_text:
                fmt.print_tags([data])
            else:
                write_success(data)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- upload ---


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@shared_options
def upload(file_path, api_key, account, use_text, quiet):
    """Upload a media file and return its media ID."""
    try:
        client, console, cfg = _get_client_and_console(api_key, quiet)
        with client:
            ssid = _resolve_account_id(client, account, cfg)
            data = upload_media(client, ssid, file_path, console)
            _output(data, use_text, fmt.print_upload_result)
    except TypefullyError as e:
        _handle_error(e, Console(quiet))


# --- batch ---


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--schedule", default=None, help="Default schedule for all drafts")
@click.option("--tag", "tags", multiple=True, help="Default tag (repeatable)")
@click.option("--share/--no-share", default=False)
@click.option("--dry-run", is_flag=True)
@click.option("--output", "output_file", default=None, type=click.Path(), help="JSON results log")
@shared_options
def batch(file_path, schedule, tags, share, dry_run, output_file, api_key, account, use_text, quiet):
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
    try:
        with open(file_path) as f:
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

        client, console, cfg = _get_client_and_console(api_key, quiet)
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
                    errors.append({
                        "index": i,
                        "message": str(e),
                        "preview": entry.posts[0][:50] if entry.posts else "",
                    })

            result = {"total": len(entries), "created": created, "errors": errors}

            if output_file:
                with open(output_file, "w") as f:
                    json.dump(result, f, indent=2)
                console.status(f"Results written to {output_file}")

            if use_text:
                fmt.print_batch_result(result)
            else:
                write_success(result)

            if errors and not created:
                sys.exit(2)
            elif errors:
                sys.exit(3)

    except TypefullyError as e:
        _handle_error(e, Console(quiet))


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
