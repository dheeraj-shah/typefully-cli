# Contributing

## Dev setup

```bash
git clone https://github.com/nicedevelopers/typefully-cli.git
cd typefully-cli
pip install -e ".[dev]"
```

## Run tests

```bash
python3 -m pytest tests/ -v
```

## Lint

```bash
ruff check src/ tests/
ruff format --check src/ tests/
```

## Project structure

```
src/typefully_cli/
  cli.py        -- Click commands and shared options
  client.py     -- Typefully API v2 HTTP client
  auth.py       -- API key resolution chain
  config.py     -- TOML config management
  console.py    -- stderr output (Rich)
  output.py     -- --text mode formatting (Rich, all user content escaped)
  batch.py      -- Batch file parser
  media.py      -- Media upload workflow
  exceptions.py -- Exception hierarchy
tests/
  test_cli.py   -- CLI command tests (CliRunner)
  test_client.py -- Client and account resolution tests
  test_batch.py -- Batch parser tests
  test_media.py -- Filename sanitization tests
  test_output.py -- Rich markup escaping tests
  test_auth.py  -- Auth chain and redaction tests
```

## Conventions

- Python 3.9+ (no walrus, no `match`)
- Line length: 100 chars
- All CLI commands use `@shared_options` and `@error_handler`
- All output.py functions escape user content with `_esc()`
- Tests mock the Typefully API (no live calls in CI)
- JSON output is the default; `--text` is opt-in

## PR process

1. Fork and create a branch
2. Make changes, add tests
3. `python3 -m pytest tests/ -v` -- all tests pass
4. `ruff check src/ tests/` -- no lint errors
5. Open a PR with a clear description

## Output contract

Any new command must follow the output contract:

- Success: `{"ok": true, "data": ...}` on stdout (exit 0)
- Error: `{"ok": false, "error": {"code": "...", "message": "...", "hint": "..."}}` on stderr (exit 1 or 2)
- Partial failure: success data on stdout + error envelope on stderr (exit 3)

## Auth for testing

Get an API key from [Typefully Settings > API](https://typefully.com/settings/api). Set it locally:

```bash
typefully config set api_key tf_your_key
typefully config set default_account YourAccount
```

Live API tests are not run in CI. For local validation, use a real account.
