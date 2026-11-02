# Changelog

## 0.5.0 (unreleased, inactive profile-sharing review)

- Add one explicit default-no opt-in for ongoing sharing of public usernames/profile URLs from all API-accessible social sets, including managed/client accounts and profiles linked later.
- Cover the documented X, LinkedIn, Bluesky, Threads, Mastodon and Substack profile fields. Read only after consent; never send credentials, names, emails, avatars, internal IDs or content.
- Sync at most daily on eligible interactive use, with bounded complete snapshots, no background daemon, arbitrary URL fetches, partial uploads or automatic retries within the day.
- Add immediate local revocation and capability-based whole-snapshot deletion, including a hash-only withdrawal tombstone to prevent delayed upload resurrection.
- Require bounded empty admission before identity lookup; enforce global D1 minute/day request, daily admission, total record, payload and per-token sync limits. Unknown withdrawal creates no record; known deletion bypasses exhausted shared quotas and cannot repeatedly extend a tombstone.
- Keep only the current snapshot with rolling 90-day expiry after the last successful sync. Active use can retain current profiles indefinitely; withdrawal removes profile data immediately.
- Profile service remains undeployed and the recipient is empty. Prepare source-only 0.5.0 aggregate collector allowlist; its production deployment and package/Homebrew publication remain separately gated.

## 0.4.0 (2026-10-29)

- Add minimal default-on usage telemetry for interactive text commands only, after a visible disclosure. The first notice invocation sends nothing.
- Disable with `TYPEFULLY_TELEMETRY=0` or `typefully config set telemetry_enabled false`. CI, noninteractive, JSON and quiet runs are excluded.
- Send only CLI version and command category to a maintainer-owned collector; store daily aggregate counts, not unique-user IDs or content. Network infrastructure still sees source IP.
- Add strict collector validation, privacy documentation and mocked telemetry tests. See `docs/telemetry.md` for retention and limits.

## 0.3.0 (2026-10-29)

- Add schema-backed `draft-payload` request-file input with offline validation, per-post fields and null/false clearing; keep `--json` as output-only.
- Add X reply/subscriber/community flags, LinkedIn first-comment/reshare fields, upload alt text and media metadata updates.
- Follow social-set pagination, accept repeated tag filters and reject negative offsets; document every public API operation and unverified MCP/product-only boundaries.


- Repair upstream monitoring: validate official public sources, expose fetch failures, deduplicate reports, and advance baselines only after successful reporting.
- Pin CI to Ubuntu 22.04 to retain Python 3.9 compatibility; isolate Fish completion tests from the real home directory.
- Extend `--quote-post-url` / `--qrt` to the documented Threads, Bluesky, Mastodon and Substack quote targets.

## 0.2.1 (2026-08-21)

- Fix trusted PyPI publishing workflow action pin.

## 0.2.0 (2026-08-21)

Sync with Typefully's official MCP and Agent Skill surface.

- Add X follower analytics with `followers`.
- Add planned drafts with `draft --plan`, `update --plan`, and `plan`.
- Add review comment threads: list, create, reply, resolve, update, delete.
- Add comment-marker-safe reads and updates.
- Add Substack Notes, X Articles, platform selection, link-preview suppression, X disclosures, and official quote-post payload fields.
- Add multi-platform draft/thread creation through `--platform`.

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
