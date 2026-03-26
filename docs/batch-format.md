# Batch File Format

The `typefully batch` command reads a plain text file and creates multiple drafts in one run.

## Structure

- **Draft separator:** `---` on its own line
- **Thread separator:** `===` on its own line (within a draft block)
- **Metadata headers:** optional key-value lines at the top of each block (before any content)

## Metadata keys

| Key | Value | Example |
|-----|-------|---------|
| `tag` | Tag slug (auto-created if it doesn't exist) | `tag: launch` |
| `schedule` | ISO 8601 datetime, `next`, or `now` | `schedule: 2026-04-01T10:00:00Z` |
| `title` | Draft title (visible in Typefully UI) | `title: Campaign post` |
| `scratchpad` | Internal notes (not published) | `scratchpad: Review before posting` |
| `media` | Comma-separated media IDs from `upload` | `media: abc123,def456` |

Metadata from CLI flags (`--schedule`, `--tag`, `--share`) applies as defaults. Per-block metadata overrides CLI defaults.

## Examples

### Simple: three standalone drafts

```
First draft content
---
Second draft content
---
Third draft content
```

### Threads: multi-post drafts

```
First post of thread
===
Second post of thread
===
Third post of thread
---
A standalone draft between threads
---
Another thread starts here
===
Second post
```

### With metadata

```
tag: launch
schedule: next
title: Product launch
Our new feature is live! Here's what it does.
===
Thread continues with details.
===
Final post with a CTA.
---
tag: announcement
schedule: 2026-04-01T10:00:00Z
media: 036b7679-290f-47aa-a5cf-c8c464c1bc71
Standalone post with an image attached.
---
A minimal draft with no metadata.
```

### Dry run

Preview what will be created without making API calls:

```bash
typefully batch posts.txt --dry-run --text
```

### With defaults

CLI flags apply to all blocks unless overridden:

```bash
typefully batch posts.txt --schedule next --tag campaign --share
```

A block with its own `schedule: 2026-04-01T10:00:00Z` header will use that instead of `next`.

## Output

JSON results log (use `--output` to save):

```json
{
  "ok": true,
  "data": {
    "created": [{"index": 0, "id": 12345, "num_posts": 3}, ...],
    "errors": []
  }
}
```

On partial failure (exit 3), `created` has the successes and `errors` has the failures.
