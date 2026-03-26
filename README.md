# typefully-cli

Manage [Typefully](https://typefully.com) drafts, threads, and publishing from your terminal. Built for AI agents. Works great for humans too.

[![PyPI](https://img.shields.io/pypi/v/typefully-cli?v=1)](https://pypi.org/project/typefully-cli/)
[![Python 3.9+](https://img.shields.io/pypi/pyversions/typefully-cli?v=1)](https://pypi.org/project/typefully-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

- **Automate publishing** -- schedule and publish from CI/CD pipelines, cron jobs, or scripts
- **Batch create** -- turn a text file into 50 drafts with one command
- **Agent-native** -- JSON output, structured errors, deterministic exit codes. Designed for Claude Code, LLM agents, and automation

## Install

```bash
pipx install typefully-cli        # recommended
uv tool install typefully-cli     # alternative
pip install typefully-cli          # fallback
```

## Quick Start

```bash
# First-time setup (interactive)
typefully config init

# Or set your API key directly (get it from typefully.com/settings/api)
typefully config set api_key tf_your_key_here

# Check auth
typefully me

# Create a draft
typefully draft "Hello world" --schedule next

# Create a thread
typefully thread "First post" "Second post" --tag launch

# Batch create from file
typefully batch posts.txt --schedule next --tag campaign

# Upload media and attach it
typefully upload photo.jpg
typefully draft "Check this out" --media <media_id>
```

## For Humans

Add `--text` to any command for readable output instead of JSON.

```bash
typefully drafts --text
typefully recent --text --since 2025-01-01
typefully get 12345 --text
```

**Other handy features:**

- `typefully open 12345` -- open a draft in your browser
- `typefully recent --format csv` -- export published posts to CSV
- `typefully config init` -- guided first-time setup

**Shell completions** -- add to your shell rc file:

```bash
# Bash
eval "$(_TYPEFULLY_COMPLETE=bash_source typefully)"

# Zsh
eval "$(_TYPEFULLY_COMPLETE=zsh_source typefully)"

# Fish
_TYPEFULLY_COMPLETE=fish_source typefully | source
```

## For Agents

Every command writes structured JSON. Success to stdout, errors to stderr. Parse with `jq`, pipe to other tools, or consume directly from an LLM agent.

### Output contract

```bash
# Success (stdout)
{"ok": true, "data": ...}

# Error (stderr)
{"ok": false, "error": {"code": "auth_failed", "message": "...", "hint": "..."}}
```

### Exit codes

| Code | Meaning | When |
|------|---------|------|
| `0` | Success | Everything worked |
| `1` | Input/auth error | Bad credentials, missing account, invalid input |
| `2` | API error | Upstream Typefully API failure |
| `3` | Partial failure | Some items in a batch/delete succeeded, others failed |

### Error codes

| Code | Trigger |
|------|---------|
| `auth_failed` | No API key found in flag, env, config, or 1Password |
| `no_account` | No account specified or account not found |
| `api_error` | Non-2xx response from Typefully API |
| `invalid_input` | Bad date format, limit out of range, single-post thread |
| `batch_parse_error` | Malformed batch file |
| `media_upload_error` | Upload failed or unsupported format |

### Partial failure (batch/delete)

When some operations succeed and some fail (exit 3):
- **stdout**: success data with `deleted`/`created` array + `errors` array
- **stderr**: `partial_failure` error envelope

When all fail (exit 2): nothing on stdout, `all_failed` on stderr.

### Common patterns

```bash
# Suppress status messages, keep errors
typefully accounts --quiet 2>/dev/null

# Extract draft IDs
typefully drafts | jq '.data.results[].id'

# Get error hint on failure
typefully me 2>/tmp/err.json || jq '.error.hint' /tmp/err.json

# Batch create and log results
typefully batch posts.txt --output results.json
```

### Flags for agents

- `--quiet` -- suppress stderr status messages (errors still shown)
- `--api-key KEY` -- pass API key directly (skips config/env lookup)
- `--account NAME` -- target a specific account (accepts name, username, or numeric ID)

## Auth

Resolution order: `--api-key` flag > `TYPEFULLY_API_KEY` env var > config file > 1Password.

Get your API key from [Typefully Settings > API](https://typefully.com/settings/api).

```bash
# Interactive setup
typefully config init

# Or manually
typefully config set api_key tf_your_key_here
typefully config set default_account MyBrand

# Optional: 1Password fallback (requires op CLI)
typefully config set onepassword_item "Typefully API"
```

## Commands

All account-scoped commands accept `--api-key`, `--account`, `--text`, `--quiet`.

| Command | Description |
|---------|-------------|
| `me` | Current user info |
| `accounts` | List connected accounts with IDs |
| `account-detail [NAME]` | Platform details for an account |
| `draft "text"` | Create a single-post draft |
| `thread "p1" "p2" ...` | Create a multi-post thread (min 2 posts) |
| `get ID` | View a draft |
| `open ID` | Open a draft in the browser |
| `update ID ["text"]` | Edit a draft (use `===` to separate thread posts) |
| `delete ID [ID ...]` | Delete one or more drafts |
| `drafts` | List drafts (`--status`, `--tag`, `--limit 1-50`, `--offset`, `--order`) |
| `recent` | Published posts (`-n 1-50`, `--since`, `--until`, `--format csv`) |
| `upload FILE` | Upload media, returns media ID |
| `tags` | List tags (`--limit 1-50`, `--offset`) |
| `tag-create "name"` | Create a tag (usually auto-created via `--tag`) |
| `batch FILE` | Batch create from text file (`--dry-run`, `--output`, `--schedule`, `--tag`) |
| `config set KEY VALUE` | Set config (api_key, default_account, onepassword_item) |
| `config init` | Interactive first-time setup |
| `config show` | Show config (secrets redacted) |
| `config path` | Print config file path |

**Draft options:** `--schedule ISO|next|now`, `--tag SLUG` (repeatable, auto-created), `--title`, `--media ID`, `--share`, `--reply-to URL`, `--scratchpad`, `--qrt URL`, `--threadify`, `--auto-retweet/--no-auto-retweet`, `--auto-plug/--no-auto-plug`, `--linkedin`, `--threads`, `--bluesky`, `--mastodon`

Run `typefully COMMAND --help` for full option details.

## Batch File Format

Drafts separated by `---`. Thread posts separated by `===`. Optional metadata headers per block.

```
tag: launch
schedule: next
First post of a thread
===
Second post
---
A standalone draft
---
tag: announcement
schedule: 2026-04-01T10:00:00Z
Another standalone draft
```

Supported metadata: `tag`, `schedule`, `title`, `scratchpad`, `media` (comma-separated IDs). See [docs/batch-format.md](docs/batch-format.md) for the full spec.

## Configuration

Config file: `~/.config/typefully/config.toml`

```toml
[auth]
api_key = "tf_..."
# onepassword_item = "Typefully API"

[defaults]
account = "MyBrand"
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
