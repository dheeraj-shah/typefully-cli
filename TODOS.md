# TODOS

Deferred items from CEO review + eng review (2026-03-26).

## P2

### MCP server
- **What:** Thin MCP server wrapping the CLI commands as tools
- **Why:** Makes typefully-cli instantly useful in Claude Code and other MCP-aware agents
- **Context:** The JSON contract is already MCP-tool-shaped -- each command maps to a tool. Typefully has an official MCP server; ours would offer more features and robustness. Wait for user demand before building.
- **Effort:** M (human: ~3 days / CC: ~1 hour)
- **Depends on:** v0.1.0 published, user feedback

## P3

### Media poll timeout handling
- **What:** Raise `MediaUploadError` or add `"timed_out": true` when polling exhausts 30 attempts
- **Why:** Currently returns a success-shaped response with status "processing" -- misleading
- **Context:** `media.py` polling loop returns last status dict silently. 60-second window covers most files; large videos could exceed it.
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
- **Why:** Currently ~800 lines and growing
- **Context:** Click supports multi-file CLI groups cleanly. Only split when it actually hurts readability.
- **Effort:** M (human: ~3 hours / CC: ~15 min)
