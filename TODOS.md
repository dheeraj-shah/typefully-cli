# TODOS

Deferred items from CEO review + eng review (2026-03-26).

## P2

### PyPI publish workflow
- **What:** `.github/workflows/publish.yml` triggered on tag push (`v*`), builds sdist + wheel, publishes to PyPI
- **Why:** Currently manual: `python -m build && twine upload`. No guard against publishing a broken artifact.
- **Context:** Hatchling build is configured. Add `twine check dist/*` step before upload. Use trusted publisher (OIDC) over stored API token.
- **Effort:** S (human: ~2 hours / CC: ~10 min)

### MCP server
- **What:** Thin MCP server wrapping the CLI commands as tools
- **Why:** Makes typefully-cli instantly useful in Claude Code and other MCP-aware agents
- **Context:** The JSON contract is already MCP-tool-shaped -- each command maps to a tool. Typefully has an official MCP server; ours would offer more features and robustness. Wait for user demand before building.
- **Effort:** M (human: ~3 days / CC: ~1 hour)
- **Depends on:** v0.1.0 published, user feedback

## P3

### Media poll timeout handling
- **What:** Raise `MediaUploadError` or add `"timed_out": true` when `poll_media` exhausts 30 attempts
- **Why:** Currently returns a success-shaped response with status "processing" -- misleading
- **Context:** `client.py:poll_media` returns last status dict silently. 60-second window covers most files; large videos could exceed it.
- **Effort:** S (human: ~1 hour / CC: ~5 min)


### `--debug` flag for HTTP request logging
- **What:** Add `--debug` flag that logs HTTP request/response details to stderr
- **Why:** No way to see what API calls are being made; helps debug auth and API issues
- **Context:** Could use httpx's event hooks or a simple logger. Should show method, URL, status code, timing.
- **Effort:** S (human: ~2 hours / CC: ~10 min)

### `poll_media` dead code cleanup
- **What:** `client.py:poll_media()` is never called; `media.py` uses an inline polling loop instead
- **Why:** Two implementations of the same logic. Either delete `poll_media` or have `media.py` call it.
- **Context:** The inline loop in `media.py` was written first; `poll_media` was added later as a cleaner API but never wired in.
- **Effort:** S (human: ~30 min / CC: ~5 min)

### TOML write escaping
- **What:** `Config.save()` interpolates raw strings into TOML without escaping quotes
- **Why:** `onepassword_item` and `default_account` are user-controlled. A value with `"` corrupts the config file silently -- next `Config.load()` fails.
- **Context:** `config.py:48-60` writes `key = "value"` via f-string. Fix: escape `"` and `\` in values, or use a TOML writer library.
- **Effort:** S (human: ~1 hour / CC: ~5 min)

### `config set` unknown key error code
- **What:** `config set nope x` raises `ValueError` which surfaces as `internal_error` instead of `invalid_input`
- **Why:** Confusing UX -- the user made an input error but sees a generic error code
- **Context:** `config.py:83` validates against `_VALID_KEYS` and raises `ValueError`. Change to `TypefullyError(code="invalid_input")` or catch `ValueError` in `error_handler`.
- **Effort:** S (human: ~15 min / CC: ~2 min)

### CLI version in error JSON envelope
- **What:** Include `"cli_version": "0.1.0"` in error JSON output
- **Why:** Helps with bug reports -- users can paste error output and version is embedded
- **Context:** `error_handler` in `cli.py` constructs the error envelope. One-line addition.
- **Effort:** S (human: ~15 min / CC: ~2 min)

### Extract shared mock helper in test_cli.py
- **What:** DRY up the mock client/console/config setup pattern repeated across test classes
- **Why:** TestDateValidation, TestLimitValidation, TestCleanErrorPayloads, TestDeletePartialFailure all build similar mocks
- **Context:** Extract a `_mock_gcc(delete_side_effects=None)` fixture or helper.
- **Effort:** S (human: ~1 hour / CC: ~5 min)

### Split cli.py when it exceeds ~1000 lines
- **What:** Split `cli.py` into `cli_config.py`, `cli_drafts.py`, `cli_batch.py` etc.
- **Why:** Currently ~760 lines and growing with cherry-picks (config init, open, csv export)
- **Context:** Click supports multi-file CLI groups cleanly. Only split when it actually hurts readability.
- **Effort:** M (human: ~3 hours / CC: ~15 min)
- **Depends on:** Cherry-pick features landing first
