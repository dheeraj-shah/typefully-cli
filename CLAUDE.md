# typefully-cli

## Overview

Python CLI wrapping the Typefully API v2. Agent-friendly structured JSON output with `--json`, structured errors on stderr, and configurable text output. See `skills/typefully-cli/SKILL.md` for current agent usage and `docs/upstream-parity.md` for evidence and limitations.

## Architecture

```
src/typefully_cli/
  cli.py        -- Click commands, shared options, error handler, payload builder
  payloads.py   -- Explicit JSON request input, local schema validation, media metadata
  request-schemas.json -- Reviewed public create/update schema snapshot
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
- **API parity:** Map each public operation in docs/upstream-parity.md. Do not claim exhaustive MCP parity; analytics and legacy convenience fields are not verified by the current public schema.

## Dev setup

```bash
pip install -e ".[dev]"
```

## Test and lint

```bash
python3 -m pytest tests/ -v
ruff check --isolated --select E4,E7,E9,F --target-version py39 --line-length 100 src/ tests/ scripts/
```

## Auth for live testing

Use existing authorized access from environment/config; never assume an account
named in documentation is a sandbox. No cloud credential is bundled with this repo.
Use local `--validate-only` and mocked tests first. Live test writes need explicit
scope and a verified social set; never publish as part of maintenance tests.

## Conventions

- Python 3.9+ compatibility (no walrus operator, no `match` statements)
- Line length: 100 chars (ruff)
- All new CLI commands get the `@shared_options` decorator and `@error_handler`
- All new output.py functions must escape user content with `_esc()`
- Tests use Click's CliRunner with mock client/console/config
- No emojis in code or docs
