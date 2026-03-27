"""Output formatting: JSON envelope (default) and Rich human-readable (--text)."""

from __future__ import annotations

from rich.console import Console as RichConsole
from rich.markup import escape as _esc
from rich.table import Table


_console = RichConsole()


def print_user(data: dict) -> None:
    _console.print(f"  Name:  {_esc(data.get('name', '?'))}")
    _console.print(f"  Email: {_esc(data.get('email', '?'))}")
    _console.print(f"  Key:   {_esc(data.get('api_key_label', '?'))}")


def print_accounts(results: list[dict]) -> None:
    table = Table(title="Social Sets")
    table.add_column("Username")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Platforms")
    for s in results:
        platforms = ", ".join(s.get("platforms", {}).keys()) if isinstance(s.get("platforms"), dict) else ""
        table.add_row(
            _esc(s.get("username", "?")),
            str(s.get("id", "?")),
            _esc(s.get("name", "")),
            _esc(platforms),
        )
    _console.print(table)


def print_account_detail(data: dict) -> None:
    _console.print(f"  Name: {_esc(data.get('name', '?'))}")
    _console.print(f"  ID:   {data.get('id', '?')}")
    team = data.get("team")
    if team:
        _console.print(f"  Team: {_esc(team.get('name', '?'))} (ID: {team.get('id', '?')})")
    platforms = data.get("platforms", {})
    if platforms:
        _console.print("\n  Connected platforms:")
        for name, info in platforms.items():
            if not info or not isinstance(info, dict):
                continue
            username = info.get("username", "?")
            profile = info.get("profile_url", "")
            _console.print(f"    \\[{_esc(name.upper())}] @{_esc(username)}")
            if profile:
                _console.print(f"      {profile}")


def print_draft(data: dict) -> None:
    _console.print(f"  ID:     {data.get('id', '?')}")
    _console.print(f"  Status: {data.get('status', '?')}")
    for key in ("created_at", "updated_at", "draft_title", "scheduled_date", "published_at"):
        val = data.get(key, "")
        if val:
            label = key.replace("_", " ").title()
            _console.print(f"  {label}: {_esc(str(val)[:19])}")
    tags = data.get("tags", [])
    if tags:
        tag_str = ", ".join(
            t.get("name", t.get("slug", "?")) if isinstance(t, dict) else str(t)
            for t in tags
        )
        _console.print(f"  Tags: {_esc(tag_str)}")
    for url_key in ("share_url", "private_url", "x_published_url", "linkedin_published_url"):
        val = data.get(url_key, "")
        if val:
            label = url_key.replace("_", " ").title()
            _console.print(f"  {label}: {val}")
    scratchpad = data.get("scratchpad_text", "")
    if scratchpad:
        _console.print(f"  Scratchpad: {_esc(scratchpad)}")
    # Posts per platform
    for platform, pdata in data.get("platforms", {}).items():
        if not isinstance(pdata, dict) or not pdata.get("enabled"):
            continue
        posts = pdata.get("posts", [])
        _console.print(f"\n  \\[{_esc(platform.upper())}] ({len(posts)} post{'s' if len(posts) != 1 else ''})")
        for i, p in enumerate(posts):
            if i > 0:
                _console.print("    ---")
            _console.print(f"    {_esc(p.get('text', '(no text)'))}")


def print_draft_short(data: dict) -> None:
    _console.print(f"  ID:     {data.get('id', '?')}")
    _console.print(f"  Status: {data.get('status', '?')}")
    share_url = data.get("share_url", "")
    if share_url:
        _console.print(f"  Share:  {share_url}")
    private_url = data.get("private_url", "")
    if private_url:
        _console.print(f"  Edit:   {private_url}")


def print_drafts_list(data: dict) -> None:
    count = data.get("count", "?")
    results = data.get("results", [])
    if not results:
        _console.print("  (none)")
        return
    _console.print(f"  Showing {len(results)} of {count} total\n")
    for d in results:
        status = d.get("status", "?")
        # Get text from platforms or preview
        text = ""
        platforms = d.get("platforms", {})
        if isinstance(platforms, dict) and "x" in platforms:
            posts = platforms.get("x", {}).get("posts", [])
            if posts:
                text = posts[0].get("text", "")
        if not text:
            text = d.get("preview", "(no text)")
        preview = text[:80] + "..." if len(text) > 80 else text
        draft_id = d.get("id", "?")
        tags = d.get("tags", [])
        tag_str = ""
        if tags:
            tag_str = " " + " ".join(
                f"#{t['name'] if isinstance(t, dict) else t}" for t in tags
            )
        _console.print(f"  \\[{_esc(status)}] {_esc(preview)} (ID: {draft_id}){_esc(tag_str)}")


def print_recent(posts: list[dict]) -> None:
    if not posts:
        _console.print("  (none)")
        return
    for d in posts:
        pub = d.get("published_at", "?")[:10]
        draft_id = d.get("id", "?")
        text = ""
        platforms = d.get("platforms", {})
        if isinstance(platforms, dict) and "x" in platforms:
            pp = platforms.get("x", {}).get("posts", [])
            if pp:
                text = "\n  ---\n".join(p.get("text", "") for p in pp)
        if not text:
            text = d.get("preview", "(no text)")
        x_url = d.get("x_published_url", "")
        _console.print(f"--- \\[{_esc(pub)}] (ID: {draft_id}) ---")
        _console.print(f"  {_esc(text)}")
        if x_url:
            _console.print(f"  -> {x_url}")
        _console.print()


def print_tags(results: list[dict]) -> None:
    if not results:
        _console.print("  (none)")
        return
    for t in results:
        _console.print(f"  {_esc(t.get('name', '?'))} (slug: {_esc(t.get('slug', '?'))})")


def print_batch_dry_run(entries: list[dict]) -> None:
    for i, e in enumerate(entries):
        n = len(e.get("posts", []))
        label = "thread" if n > 1 else "single"
        preview = _esc(e["posts"][0][:60]) if e.get("posts") else "(empty)"
        sched = e.get("schedule") or "(no schedule)"
        tags = ", ".join(e.get("tags", [])) or "(no tags)"
        _console.print(f"  \\[{i+1}] {label} ({n} post{'s' if n > 1 else ''}) | {_esc(sched)} | {_esc(tags)}")
        _console.print(f"      {preview}")
        _console.print()


def print_batch_result(result: dict) -> None:
    total = result.get("total", 0)
    created = result.get("created", [])
    errors = result.get("errors", [])
    _console.print(f"\n  Done: {len(created)} created, {len(errors)} errors (of {total} total)")


def print_delete_result(result: dict) -> None:
    deleted = result.get("deleted", [])
    errors = result.get("errors", [])
    _console.print(f"  Deleted: {len(deleted)}, Errors: {len(errors)}")


def print_upload_result(data: dict) -> None:
    _console.print(f"  Media ID: {data.get('media_id', '?')}")
    _console.print(f"  Status:   {data.get('status', '?')}")


def print_analytics(data: dict) -> None:
    results = data.get("results", [])
    if not results:
        _console.print("  (no analytics data)")
        return
    table = Table(title="Post Analytics")
    table.add_column("Post ID")
    table.add_column("Published", style="dim")
    table.add_column("Text", max_width=50)
    table.add_column("Impressions", justify="right")
    table.add_column("Likes", justify="right")
    table.add_column("Replies", justify="right")
    table.add_column("Reposts", justify="right")
    table.add_column("Clicks", justify="right")
    for p in results:
        text = _esc(p.get("text", "")[:50])
        table.add_row(
            str(p.get("id", "?")),
            str(p.get("published_at", "?"))[:10],
            text,
            str(p.get("impressions", 0)),
            str(p.get("likes", 0)),
            str(p.get("comments", 0)),
            str(p.get("reposts", p.get("shares", 0))),
            str(p.get("link_clicks", p.get("clicks", 0))),
        )
    _console.print(table)


def print_queue(data: dict) -> None:
    slots = data.get("slots", data.get("results", []))
    if not slots:
        _console.print("  (empty queue)")
        return
    for slot in slots:
        time_str = slot.get("time", slot.get("scheduled_date", "?"))
        draft = slot.get("draft")
        if draft:
            draft_id = draft.get("id", "?")
            preview = draft.get("preview", "")[:60]
            _console.print(f"  [{_esc(str(time_str)[:16])}] {_esc(preview)} (ID: {draft_id})")
        else:
            _console.print(f"  [{_esc(str(time_str)[:16])}] (empty slot)")


def print_queue_schedule(data: dict) -> None:
    rules = data.get("rules", [])
    if not rules:
        _console.print("  (no schedule rules)")
        return
    _console.print("  Queue schedule:")
    for rule in rules:
        hour = rule.get("h", 0)
        minute = rule.get("m", 0)
        days = rule.get("days", [])
        days_str = ", ".join(days) if days else "every day"
        _console.print(f"    {hour:02d}:{minute:02d} -- {_esc(days_str)}")


def print_linkedin_resolve(data: dict) -> None:
    mention = data.get("mention_text", "")
    name = data.get("name", "?")
    _console.print(f"  Organization: {_esc(name)}")
    if mention:
        _console.print(f"  Mention text: {_esc(mention)}")
    _console.print("  (Copy the mention text into your LinkedIn post)")


def print_media_status(data: dict) -> None:
    _console.print(f"  Media ID: {data.get('media_id', data.get('id', '?'))}")
    _console.print(f"  Status:   {data.get('status', '?')}")
    url = data.get("url", "")
    if url:
        _console.print(f"  URL:      {url}")