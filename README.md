# typefully-cli

Publish to X, LinkedIn, Bluesky, Threads, Mastodon, Substack Notes, and X Articles from your terminal. Goes from idea to post without opening a browser.

[![PyPI](https://img.shields.io/pypi/v/typefully-cli.svg)](https://pypi.org/project/typefully-cli/)
[![Python 3.9+](https://img.shields.io/pypi/pyversions/typefully-cli.svg)](https://pypi.org/project/typefully-cli/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Why

Typefully's web UI is great for one post. Try pushing 100s across brand accounts and personal. I built a CLI to fix that, battle-tested it for 2 months, and open sourced it.

- **Multi-platform, multi-account** -- push to X, LinkedIn, Bluesky, Threads, Mastodon across any number of accounts
- **Batch create** -- prompt an AI, schedule 50 posts. One command.
- **Queue and analytics** -- see what's scheduled and what's performing, without opening a browser
- **Agent-compatible** -- JSON output, structured errors, deterministic exit codes for scripts and AI agents

## Install

```bash
brew install dheeraj-shah/tap/typefully-cli   # macOS (recommended)
pipx install typefully-cli                     # any OS
uv tool install typefully-cli                  # alternative
pip install typefully-cli                      # fallback
```

> **Tip:** `alias tf=typefully` in your shell rc. Your future self will thank you around draft #40.

## Quick Start

```bash
typefully config init                              # first-time setup
typefully draft "Hello world" --schedule next      # create and schedule a draft
typefully thread "First" "Second" --tag launch     # create a thread
typefully batch posts.txt --schedule next          # the reason this CLI exists
```

<details>
<summary>More examples</summary>

```bash
# Post to all connected platforms
typefully draft "Big announcement" --all --schedule next

# Read post content from a file
typefully draft --file post.txt --schedule next

# Check analytics
typefully analytics --start-date 2026-01-01
typefully followers --start-date 2026-01-01

# View your posting queue
typefully queue --start-date 2026-11-05 --end-date 2026-11-12

# Shell completions
typefully completions install
```

</details>

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

## For Agents

Built for humans first, but your AI agent can use it too. Every command supports `--json` for structured output. Pair with `--quiet` to suppress stderr status messages.

```bash
# JSON output mode
typefully drafts --json --quiet

# Extract draft IDs
typefully drafts --json | jq '.data.results[].id'

# Batch create and log results
typefully batch posts.txt --json --output results.json
```

To make JSON the default (no need for `--json` every time):

```bash
typefully config set output_format json
```

<details>
<summary>Output contract and error codes</summary>

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
| `media_processing_timeout` | Upload succeeded but processing did not finish before `--timeout`; poll the media ID in the hint |

### Partial failure (batch/delete)

When some operations succeed and some fail (exit 3):
- **stdout**: success data with `deleted`/`created` array + `errors` array
- **stderr**: `partial_failure` error envelope

When all fail (exit 2): nothing on stdout, `all_failed` on stderr.

</details>

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

Human-readable output by default. Add `--json` to any command for structured JSON.

All account-scoped commands accept `--api-key`, `--account`, `--json`, `--quiet`.

<details>
<summary><strong>Account</strong></summary>

| Command | Description |
|---------|-------------|
| `me` | Current user info |
| `accounts` | List connected accounts with IDs |
| `account-detail [NAME]` | Platform details for an account |

</details>

<details>
<summary><strong>Creating</strong></summary>

| Command | Description |
|---------|-------------|
| `draft "text"` | Create a single-post draft |
| `thread "p1" "p2" ...` | Create a multi-post thread (min 2 posts) |
| `batch FILE` | Batch create from text file (`--dry-run`, `--output`, `--schedule`, `--tag`) |

</details>

<details>
<summary><strong>Managing</strong></summary>

| Command | Description |
|---------|-------------|
| `get ID` | View a draft |
| `open ID` | Open a draft in the browser |
| `update ID ["text"]` | Edit a draft (use `===` to separate thread posts) |
| `delete ID [ID ...]` | Delete one or more drafts |
| `publish ID` | Start immediate publication; poll `get ID` until `publish_state` is `finished` |
| `schedule ID` | Schedule a draft (`--time ISO\|next`, default: next) |
| `plan ID --time ISO\|next` | Place draft on calendar without scheduling publication |
| `comments list\|create\|reply\|resolve\|update\|delete` | Manage draft review comments |

</details>

<details>
<summary><strong>Viewing</strong></summary>

| Command | Description |
|---------|-------------|
| `drafts` | List drafts (`--status`, `--tag`, `--limit`, `--offset`, `--order`) |
| `recent` | Published posts (`-n`, `--since`, `--until`, `--format csv`) |
| `analytics` | Post analytics (`--platform`, `--start-date`, `--end-date`, `--include-replies`) |
| `followers` | Follower analytics (`--platform`, `--start-date`, `--end-date`) |
| `queue` | View posting queue (requires `--start-date` and `--end-date`) |
| `queue-schedule get\|set` | Get or set posting times (`--rules` for set) |

</details>

<details>
<summary><strong>Media</strong></summary>

| Command | Description |
|---------|-------------|
| `upload FILE` | Upload media (`--no-wait`, `--timeout`) |
| `media-status ID` | Check media processing status |
| `linkedin-resolve URL` | Resolve LinkedIn company URL to @mention syntax |

</details>

<details>
<summary><strong>Tags</strong></summary>

| Command | Description |
|---------|-------------|
| `tags` | List tags (`--limit`, `--offset`) |
| `tag-create "name"` | Create a tag (usually auto-created via `--tag`) |

</details>

<details>
<summary><strong>Config</strong></summary>

| Command | Description |
|---------|-------------|
| `config set KEY VALUE` | Set config (api_key, default_account, output_format, onepassword_item) |
| `config init` | Interactive first-time setup |
| `config show` | Show config (secrets redacted) |
| `config path` | Print config file path |
| `completions install` | Auto-install shell completions (bash/zsh/fish) |
| `completions show` | Print raw completion script |

</details>

### Platforms

| Platform | Flag |
|----------|------|
| X (Twitter) | Always enabled |
| LinkedIn | `--linkedin` |
| Threads | `--threads` |
| Bluesky | `--bluesky` |
| Mastodon | `--mastodon` |
| Substack Notes | `--substack` or `--platform substack` |
| X Article | `--platform x_article --content-markdown "..."` |
| All connected | `--all` |

**Draft options:** `--schedule ISO|next|now`, `--plan ISO|next`, `--platform x,linkedin`, `--tag SLUG` (repeatable, auto-created), `--title`, `--media ID`, `--share`, `--reply-to URL`, `--scratchpad`, `--qrt URL`, `--threadify`, `--auto-retweet/--no-auto-retweet`, `--auto-plug/--no-auto-plug`, `--file` (read from file), `--community ID` (X community), `--paid-partnership`, `--made-with-ai`, `--hide-link-preview`.

**Update options:** all draft options plus `--append` (add posts to existing thread)

Run `typefully COMMAND --help` for full option details.

## Troubleshooting

**"No API key found"** -- Run `typefully config init` or set `TYPEFULLY_API_KEY` env var. Get your key from [typefully.com/settings/api](https://typefully.com/settings/api).

**"Account not found"** -- Check available accounts with `typefully accounts`. Set a default with `typefully config set default_account YourAccount`.

**"API returned 429"** -- Rate limited. The CLI auto-throttles batch operations, but if you're scripting rapid calls, add delays between requests.

**"S3 upload failed"** -- Check file size and format. Supported: jpg, jpeg, png, webp, gif, mp4, mov, pdf.

## Configuration

Config file: `~/.config/typefully/config.toml`

```toml
[auth]
api_key = "tf_..."
# onepassword_item = "Typefully API"

[defaults]
account = "MyBrand"
output_format = "text"   # or "json" for agent/script use
```

## Usage telemetry

Version 0.4.0 and later count CLI version and command category only through a
maintainer-owned collector, after a visible notice. The first notice invocation
sends nothing. Version 0.3.0 installations are unchanged.
Disable with `TYPEFULLY_TELEMETRY=0` or
`typefully config set telemetry_enabled false`. See [privacy and activation details](docs/telemetry.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT

## Upstream compatibility maintenance

The public-source monitor opens issues for upstream changes or failed checks; it does not
implement or merge updates. See the [source and capability baseline](docs/upstream-parity.md)
for monitored sources, known limits, and how maintenance coordinates with Dependabot.

Native quotes route to the matching selected platform (the existing `--qrt` alias still works):

```sh
typefully draft "My take" --platform bluesky --quote-post-url https://bsky.app/profile/example.com/post/abc
```

Threads, Bluesky, Mastodon and Substack quotes apply to the first new post. Existing X
thread behavior is retained. See [quote compatibility notes](docs/quote-parity.md).

### Complete request input and media alt text

`draft-payload create --file draft.json --validate-only` validates the reviewed public
API schema offline. Remove `--validate-only` and select `--account` to submit.
Use `draft-payload update --draft-id ID --file update.json` for per-post settings,
explicit null/false clearing, or advanced fields. This is **request input**;
`--json` on existing commands only controls output. The new advanced commands
always emit JSON. Platform arrays replace content: retain posts/comment markers
and settings you want to keep. `publish_at: "now"` really requests publication.

`upload image.png --alt-text "Description"` sets alt text before attachment.
`media-update MEDIA_ID --alt-text "New description"` or `--clear-alt-text` changes
stored media; previously attached drafts keep their existing metadata snapshot.
See [the full public capability matrix and remaining MCP boundaries](docs/upstream-parity.md).

### Publication progress, queue and review comments

Immediate publication is asynchronous: `publish ID` or `--schedule now` can return
`status: draft`, `publish_state: in_progress` and null publication URLs. The request
was accepted; use `get ID` until `publish_state` is `finished`, then inspect the
status and platform URLs. Human output displays this progress; JSON keeps the
upstream fields. Planned drafts never auto-publish until explicitly confirmed.

`queue` requires both `--start-date YYYY-MM-DD` and `--end-date YYYY-MM-DD` in the
account timezone. Human output includes free slots, scheduled drafts and inert
planned drafts. `queue-schedule set --rules` replaces the entire schedule; `[]`
clears it. Hours are 0..23, minutes 0..59, days mon..sun, with no duplicate day/time
pairs. Even `queue-schedule get` can initialize missing server defaults.

Review comments use `comments create ID --post-index 0 --selected-text "substring"
--text "Review body"`, or `--platform x_article` without a post index for articles.
`--text` is the comment body on create/reply/update; use `--human` for their human
output override and `--json` for structured output. Comment bodies are 1..10000
characters, selected text 1..50000, and occurrence 0..10000. Thread/comment/media
IDs must be UUIDs. `tag-create` accepts names of 1..32 characters.

Uploads stop immediately on terminal processing failure and include the server's
reason. A processing timeout reports `media_processing_timeout` with the media ID
and polling command; it does not imply the upload failed. `media-status --text`
shows current error, alt text and original media URL when supplied by the API.

### Optional connected profiles (0.5.0)

Profile sharing is off by default. `typefully community share-profiles` offers one
explicit opt-in covering every account your API key can access, including
team/client accounts and profiles linked later. It shares only documented public
usernames/profile URLs for X, LinkedIn, Bluesky, Threads, Mastodon and Substack.
Declining triggers no identity lookup or submission. You must have permission to
share the managed/client profiles covered by that consent.

After opt-in, a complete current snapshot syncs at most daily during eligible
interactive CLI use. Each successful sync restarts a rolling 90-day expiry;
active use can retain current profiles indefinitely. `community status` is local;
`community withdraw-profiles` stops sync immediately and removes the remote
profiles using the private local receipt. Anonymous usage counts remain separate.
See [scope, data, ongoing sync, retention and removal](docs/profile-sharing.md)
and the [0.5.0 activation/publication plan](docs/release-0.5.0.md).

### Agent skill

The repository's [Typefully CLI skill](skills/typefully-cli/SKILL.md) describes these
Python CLI commands, local validation and authorization boundaries. It is distinct
from Typefully's official JavaScript agent skill. Check the installed CLI's help:
maintenance-branch features are not available in an older published package until
an approved release is made.
