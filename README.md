# typefully-cli

CLI for the [Typefully](https://typefully.com) API. Create drafts, threads, batch publish, upload media, manage tags -- from the terminal or via AI agents.

**Agent-first design:** JSON output by default, structured errors, deterministic behavior. Works natively with Claude Code, automation scripts, and CI/CD.

## Install

```bash
pipx install typefully-cli        # recommended
uv tool install typefully-cli     # alternative
pip install typefully-cli          # fallback
```

## Auth

Get your API key from [Typefully Settings > API](https://typefully.com/settings/api).

Three options (checked in this order):

```bash
# Option 1: Environment variable
export TYPEFULLY_API_KEY=tf_your_key_here

# Option 2: Config file
typefully config set api_key tf_your_key_here

# Option 3: Per-command flag
typefully me --api-key tf_your_key_here
```

Optional: 1Password fallback (if `op` CLI is installed):
```bash
typefully config set onepassword_item "Typefully API"
```

## Quick Start

```bash
# Check auth
typefully me

# Set a default account
typefully config set default_account MyBrand

# Create a draft
typefully draft "Hello world" --schedule next

# Create a thread
typefully thread "First post" "Second post" --tag launch

# Batch create from file
typefully batch posts.txt --schedule next --tag campaign

# Upload media
typefully upload photo.jpg
typefully draft "Check this out" --media <media_id>

# Human-readable output
typefully drafts --text
```

## Output Contract

**JSON by default.** Every command writes one JSON object to stdout:

```json
{"ok": true, "data": ...}
```

**Errors to stderr.** On failure, the last line of stderr is:

```json
{"ok": false, "error": {"code": "auth_failed", "message": "...", "hint": "..."}}
```

**`--text`** switches to human-readable Rich output. **`--quiet`** suppresses status messages on stderr (errors still shown).

Exit codes: `0` success, `1` auth/config error, `2` API error, `3` partial failure (batch/delete).

## Commands

All account-scoped commands accept: `--api-key`, `--account`, `--text`, `--quiet`

### Config

| Command | Description |
|---------|-------------|
| `config set KEY VALUE` | Set config value (api_key, default_account, onepassword_item) |
| `config show` | Show config (secrets redacted) |
| `config path` | Print config file path |

### Account

| Command | Description |
|---------|-------------|
| `me` | Current user info |
| `accounts` | List connected social sets with IDs |
| `account-detail [NAME]` | Platform details for an account |

Account resolution: `--account` flag > config `default_account` > error. Accepts name, username, or numeric ID.

### Drafts

| Command | Description |
|---------|-------------|
| `draft "text"` | Create a single-post draft |
| `thread "p1" "p2" ...` | Create a multi-post thread (2+ posts required) |
| `get DRAFT_ID` | View draft details |
| `update DRAFT_ID ["text"]` | Edit draft (text supports `===` for threads) |
| `delete ID1 [ID2 ...]` | Delete drafts |
| `drafts` | List drafts (with `--status`, `--tag`, `--limit`, `--offset`, `--order`) |
| `recent` | Published posts (with `-n`, `--since`, `--until`) |

**Draft options:** `--schedule ISO|next|now`, `--tag SLUG` (repeatable, auto-created), `--title`, `--media ID`, `--share`, `--reply-to URL`, `--scratchpad`, `--qrt URL`, `--threadify`, `--auto-retweet/--no-auto-retweet`, `--auto-plug/--no-auto-plug`, `--linkedin`, `--threads`, `--bluesky`, `--mastodon`

### Tags

| Command | Description |
|---------|-------------|
| `tags` | List tags |
| `tag-create "name"` | Create a tag (usually auto-created via `--tag`) |

### Media

| Command | Description |
|---------|-------------|
| `upload /path/to/file` | Upload media, returns media_id |

### Batch

```bash
typefully batch posts.txt --schedule next --tag launch --dry-run
```

| Option | Description |
|--------|-------------|
| `--schedule` | Default schedule for all drafts |
| `--tag` | Default tag (repeatable) |
| `--share/--no-share` | Enable share links |
| `--dry-run` | Preview without creating |
| `--output FILE` | Write JSON results log |

## Batch File Format

Drafts separated by `---` on its own line. Thread posts separated by `===`.
Optional metadata at top of each block:

```
tag: launch
schedule: 2026-03-25T10:00:00Z
title: Campaign post
scratchpad: Internal notes
media: media_id_1,media_id_2
First tweet
===
Second tweet (same thread)
---
A standalone tweet
---
schedule: next
tag: announcement
Another standalone tweet
```

## Configuration

Config file: `~/.config/typefully/config.toml`

```toml
[auth]
api_key = "tf_..."
# onepassword_item = "Typefully API"

[defaults]
account = "MyBrand"
```

## Agent Usage

Designed for AI coding agents (Claude Code, etc.):

```bash
# Pure JSON, no decoration
typefully accounts --quiet 2>/dev/null

# Parse with jq
typefully drafts | jq '.data.results[].id'

# Structured errors for programmatic handling
typefully me 2>/tmp/err.json || cat /tmp/err.json | jq '.error.hint'
```

## License

MIT
