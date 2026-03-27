# typefully-cli

## Overview

Python CLI wrapping the Typefully API v2. Agent-first design: JSON output by default, structured errors on stderr, deterministic behavior. 24 Click commands for drafts, threads, batch, media, analytics, queue, LinkedIn, tags, accounts, config, completions.

## Architecture

```
src/typefully_cli/
  cli.py        -- 24 Click commands, shared options, error handler, payload builder
  client.py     -- httpx wrapper over Typefully API v2 (rate-limited, account resolution)
  completions.py -- Shell completions install/show (bash/zsh/fish)
  auth.py       -- API key resolution chain: flag > env > config > 1Password
  config.py     -- TOML config at ~/.config/typefully/config.toml
  console.py    -- stderr output (status, warnings, errors) via Rich
  output.py     -- Rich --text formatting (all user content escaped via rich.markup.escape)
  batch.py      -- Batch file parser (--- separators, === threads, metadata headers)
  media.py      -- S3 presigned upload + poll workflow
  exceptions.py -- TypefullyError hierarchy with structured JSON serialization
```

## Key patterns

- **Output contract:** Success -> `{"ok": true, "data": ...}` on stdout. Errors -> `{"ok": false, "error": {...}}` on stderr. Exit codes: 0 success, 1 input/auth, 2 API, 3 partial failure.
- **Rich markup safety:** All user/API text in output.py is wrapped with `_esc()` (rich.markup.escape) before printing. Never pass raw API content to `_console.print()`.
- **Input validation:** Dates via `_validate_date()`, limits via `_validate_limit()`, timezones via `_validate_timezone()`, platforms via `_validate_platforms()`. All raise on invalid input with exit 1.
- **Default platforms:** Config `default_platforms` (e.g. `x,linkedin`) auto-applied on `draft`/`thread` when no platform flags passed. Explicit flags override defaults.
- **Timezone conversion:** Config `timezone` (IANA name) converts naive schedule datetimes to UTC before API call. Already-tz-aware values pass through unchanged.
- **Partial failure:** Delete and batch loops catch per-item errors. `_handle_multi_result()` handles the 3-branch contract (all succeed / partial / all fail).
- **Error sanitization:** `APIError.user_message` property strips raw upstream bodies from stdout payloads. Full details stay on stderr.
- **API parity:** Tracks all Typefully API v2 endpoints including analytics, queue management, and LinkedIn org resolution.

## Dev setup

```bash
pip install -e ".[dev]"
```

## Test and lint

```bash
python3 -m pytest tests/ -v
ruff check src/ tests/
```

## Auth for live testing

Config at `~/.config/typefully/config.toml`. Test account: BungeeCEO.

```bash
typefully config set api_key tf_...
typefully config set default_account BungeeCEO
typefully config set default_platforms x,linkedin
typefully config set timezone Asia/Kolkata
```

## Conventions

- Python 3.9+ compatibility (no walrus operator, no `match` statements)
- Line length: 100 chars (ruff)
- All new CLI commands get the `@shared_options` decorator and `@error_handler`
- All new output.py functions must escape user content with `_esc()`
- Tests use Click's CliRunner with mock client/console/config
- No emojis in code or docs
