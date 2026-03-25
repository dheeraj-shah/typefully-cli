"""Batch file parser for the ---/=== format."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from typefully_cli.exceptions import BatchParseError

METADATA_KEYS = {"schedule", "tag", "title", "scratchpad", "media"}


@dataclass
class BatchEntry:
    posts: list[str]
    schedule: str | None = None
    tags: list[str] = field(default_factory=list)
    title: str | None = None
    scratchpad: str | None = None
    media_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"posts": self.posts}
        if self.schedule:
            d["schedule"] = self.schedule
        if self.tags:
            d["tags"] = self.tags
        if self.title:
            d["title"] = self.title
        if self.scratchpad:
            d["scratchpad"] = self.scratchpad
        if self.media_ids:
            d["media_ids"] = self.media_ids
        d["type"] = "thread" if len(self.posts) > 1 else "single"
        d["post_count"] = len(self.posts)
        return d


def parse_batch_file(content: str) -> list[BatchEntry]:
    """Parse a batch file into entries.

    Format:
    - Blocks separated by --- on its own line
    - Thread posts separated by === on its own line within a block
    - Metadata lines at top of each block: schedule:, tag:, title:, scratchpad:, media:
    """
    blocks = re.split(r"\n---\n", content.strip())
    entries: list[BatchEntry] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        schedule = None
        tags: list[str] = []
        title = None
        scratchpad = None
        media_ids: list[str] = []
        post_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            match = re.match(r"^(\w+):\s*(.+)$", stripped)
            if match and match.group(1).lower() in METADATA_KEYS:
                key = match.group(1).lower()
                val = match.group(2).strip()
                if key == "schedule":
                    schedule = val
                elif key == "tag":
                    tags.append(val)
                elif key == "title":
                    title = val
                elif key == "scratchpad":
                    scratchpad = val
                elif key == "media":
                    media_ids = [m.strip() for m in val.split(",") if m.strip()]
            else:
                post_lines.append(line)

        post_text = "\n".join(post_lines).strip()
        if not post_text:
            continue

        thread_parts = re.split(r"\n===\n", post_text)
        posts = [p.strip() for p in thread_parts if p.strip()]

        if not posts:
            continue

        entries.append(
            BatchEntry(
                posts=posts,
                schedule=schedule,
                tags=tags,
                title=title,
                scratchpad=scratchpad,
                media_ids=media_ids,
            )
        )

    if not entries:
        raise BatchParseError("No valid entries found in batch file")

    return entries


def merge_defaults(
    entries: list[BatchEntry],
    default_schedule: str | None = None,
    default_tags: tuple[str, ...] = (),
) -> None:
    """Apply command-line defaults to entries missing metadata."""
    for entry in entries:
        if not entry.schedule and default_schedule:
            entry.schedule = default_schedule
        if default_tags:
            existing = {t.lower() for t in entry.tags}
            for t in default_tags:
                if t.lower() not in existing:
                    entry.tags.append(t)
