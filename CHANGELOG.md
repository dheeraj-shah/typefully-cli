# Changelog

## 0.1.0 (2026-03-26)

Initial release.

### Commands
- `config set`, `config show`, `config path` -- manage configuration
- `me` -- show authenticated user
- `accounts`, `account-detail` -- list and inspect connected social sets
- `draft`, `thread` -- create single posts and multi-post threads
- `get`, `update`, `delete` -- manage existing drafts
- `drafts` -- list drafts with filtering (status, tag, limit, offset, order)
- `recent` -- list published posts with date range pagination
- `tags`, `tag-create` -- list and create tags (auto-created via `--tag`)
- `upload` -- upload media files (S3 presigned URL + poll)
- `batch` -- batch create drafts/threads from text file with dry-run support

### Features
- Agent-first JSON output by default, `--text` for human-readable Rich output
- Structured error JSON on stderr with exit codes (0/1/2/3)
- Auth chain: `--api-key` flag > `TYPEFULLY_API_KEY` env var > config file > 1Password
- Account resolution by name, username, or numeric ID
- Partial failure handling for delete and batch (exit 3 with both streams)
- Cross-platform posting: X, LinkedIn, Threads, Bluesky, Mastodon
- Media filename sanitization (spaces/special chars replaced with `_`)
- Rate limiting on batch operations (0.3s between requests)

### QA fixes
- Rich markup escaping for all user/API content in `--text` mode
- Date validation for `--since` / `--until` (YYYY-MM-DD required)
- Local limit validation (1-50) for `drafts`, `tags`, `recent`
- Clean error payloads in partial-failure stdout (no raw upstream bodies)
- README accuracy: limit caps, date validation, tag/media lifecycle scope
