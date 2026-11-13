# Typefully capability review: 2026-11-13

Reviewed existing draft PR #18 at `ab11733efda6e052fcd12512a3cde336dab8062d`
and main `b2d57487bf043e70587438ea079c5ae75818330f` (0.5.0). This continues
that branch, not a new PR or release. All public operation and platform rows below
were reviewed against current official sources and the implemented client/CLI/raw
payload surfaces, including previously unresolved boundaries.

## Fresh evidence

- https://typefully.com/docs/api fetched in the cloud. The embedded OpenAPI 3.1.0,
  API 2.0.0 document has 16 paths and 24 HTTP operations. All 22 bundled request
  components match the current schema after the monitor's documented transport
  normalization (examples and Next-flight description placeholders only). This
  is not a claim that the entire downloaded document is byte-identical.
- Official `typefully/agent-skills` cloned at `badd2a8`; its JavaScript command
  implementation and linked platform/quote/comment guidance were reviewed.
- Current MCP guide still describes OAuth/Streamable HTTP and draft/media/tag/
  account/queue operations. No authenticated tool inventory was available or
  authentication attempted. A fresh unauthenticated MCP request returned HTTP 401
  (authentication required). Historical tool inventory is not current proof.
- Current changelog's latest visible item remains October 28: Substack video and
  mentions. Product-only polls do not establish a writable public API contract.
- Existing draft-branch monitor fetched and validated all five sources locally
  successfully, including embedded OpenAPI. This was a fresh temporary cache:
  initialized baselines, not evidence of unchanged remote monitoring history.

## Newly repaired behavior

1. `draft --plan` now applies the configured timezone to naive timestamps, just
   like `draft --schedule`, `update --plan` and `plan --time`. Explicit timezone
   offsets and `next` are preserved; planning never becomes publishing.
2. Draft-list/recent human output and recent CSV accept the documented nullable
   `preview`/`published_at` values without an internal error. Historical enriched
   responses with a null X platform safely fall back to preview text.
3. The response schema explicitly permits null platform configurations. Appending
   to a selected null platform now behaves like an absent platform; media-only
   updates without existing posts report `invalid_input` before PATCH rather than
   an internal exception. No unrequested platform content is invented.

No new endpoints or network features were inferred. Media-only creation remains
available through validated raw payloads; the dedicated text command retains its
existing text requirement rather than assuming all platform eligibility rules.

## Complete operation matrix

Paths are relative to `/v2`; `S` is `/social-sets/{social_set_id}` and `D` is
`S/drafts/{draft_id}`. Implemented/tested means offline regression coverage and
reviewed routing; it does not mean live all-account or all-platform execution.

| Public operation(s) | Dedicated CLI / raw request surface | Current review and tests |
| --- | --- | --- |
| GET `/me` | `me` | Current user and API key label; existing structured output/error tests. |
| GET `/social-sets` | `accounts`, account resolution | Auto-paginates 50-item pages; cache/pagination tests. Dedicated output retains the established list shape rather than the API pagination envelope. |
| GET `S/` | `account-detail` | All documented platform objects pass through JSON. Human output now includes `publishing_quota` used/remaining/reset fields, including `unlimited`. |
| GET `S/drafts` | `drafts`, `recent` | Limit 1..50, offset >=0, repeated tag slugs, all six statuses and eight sort orders. New local enum validation; JSON preserves the API envelope; human/CSV nullable-preview and date rendering is regression-tested. `recent` filters published dates locally and paginates date ranges. |
| POST `S/drafts` | `draft`, `thread`, `batch`; `draft-payload create` | All seven platform keys, metadata, scheduling/planning and sharing covered by the reviewed snapshot. Raw input preserves per-post fields/null/false; offline validation and transport tests. |
| GET `D` | `get`, `open` | Comment markers retained by default; display-only exclusion flag. Human output now shows X Article Markdown, all platform publication URLs and `publish_state`. |
| PATCH `D` | `update`, `publish`, `schedule`, `plan`; `draft-payload update` | Raw input preserves explicit null/false/empty arrays and force-overwrite choice. Null selected-platform append/media handling is regression-tested. Nullable platform dictionaries and null article placeholders now validate without internal errors. Async publication progress is displayed, with manual `get` polling guidance. |
| DELETE `D` | `delete` | Existing single/multiple delete and partial-failure contract; no maintenance content deletion. |
| POST `S/media/upload` | `upload` | Filename sanitization now respects 255 characters. Alt text <=1000. S3 uses raw PUT bytes without Typefully auth or Content-Type headers. Mocked processing now stops on `failed` and preserves the reason; timeout is a distinct structured error with a polling ID. |
| GET `S/media/{media_id}` | `media-status` | New UUID validation; human output displays `error_reason`, `alt_text`, and `media_urls.original`, preserving the old top-level URL fallback. JSON remains unchanged. |
| PATCH `S/media/{media_id}` | `media-update` | UUID validation, <=1000-character replacement, explicit null clearing. Already-attached drafts retain their snapshot until content is explicitly resent. |
| GET `S/tags` | `tags` | Limit/offset controls. Dedicated JSON retains the established results-list shape. Automatic tag discovery paginates. |
| POST `S/tags` | `tag-create`, automatic tag creation | Existing exact slugs take priority over display names. Name lookup paginates; auto-creation consumes the server-returned slug. Aliases deduplicate in draft/thread/update/batch payloads, and failures stop before draft writes. New names remain 1..32 characters; slugs are never guessed. |
| GET `S/queue/schedule` | `queue-schedule get` | May initialize missing defaults on the server, despite its read-style name. Never used as a non-mutating account check. |
| PUT `S/queue/schedule` | `queue-schedule set --rules` | Full replacement, including `[]`. New local array/object, unknown-field, integer hour/minute, non-empty weekday list and duplicate day/time checks before auth. No timezone-update field is invented. |
| GET `S/queue` | `queue --start-date ... --end-date ...` | Required valid dates, ordered range and >62-day rejection. Account timezone governs dates; exact boundary/account rules remain server-authoritative. Human output now reads `days[].items[].at`, shows free slots and distinguishes inert planned drafts from scheduled drafts; legacy shapes still render. |
| GET `S/linkedin/organizations/resolve` | `linkedin-resolve URL` | Company/school URL to organization metadata and mention syntax. Resolver-only, not general search. Existing routing/output coverage. |
| GET `D/comment-threads` | `comments list` | Limit/offset, seven platform filters and unresolved/resolved/all statuses. New local enum checks; unresolved remains default. |
| POST `D/comment-threads` | `comments create` | Post index or standalone article anchor; selected text 1..50000, body 1..10000, occurrence 0..10000. Exact substring, LinkedIn atomic mention and article overlap rules remain server-side. |
| POST `D/comment-threads/{thread}/comments` | `comments reply` | UUID/body validation and mocked request coverage. |
| POST `D/comment-threads/{thread}/resolve` | `comments resolve` | UUID validation; server controls authorship/access and anchor removal. |
| PATCH `D/comment-threads/{thread}/comments/{comment}` | `comments update` | Both UUIDs and body validated; authorship remains server-side. |
| DELETE `D/comment-threads/{thread}/comments/{comment}` | `comments delete ID THREAD COMMENT` | Both UUIDs validated. Deleting the root comment can delete its whole thread. |
| DELETE `D/comment-threads/{thread}` | `comments delete ID THREAD` | UUID validated; whole-thread deletion removes anchors. |

The three comment-body commands previously collided with shared output `--text`,
preventing valid body parsing. They now keep `--text BODY` and expose `--human`
for the output override; `--json` and the success/error envelopes are unchanged.
Tests cover valid body parsing, boundary lengths, article anchors, rejection before
auth, and unique CLI help options.

## Writable fields and platforms

| Capability | Dedicated options | Raw schema support / remaining server checks |
| --- | --- | --- |
| X | Reply-to URL, community, follower sharing true/false, quotes, reply-settings enum/null, subscribers-only true/false, disclosure labels | Per-post text/media, disclosure false/null and other nullable fields are available through raw input. Premium/account rules and external quote/reply validity stay server-side. |
| LinkedIn | Platform targeting, first comment/null/empty clearing, reshare URL/URN/null, link-preview hiding; organization resolver | Raw input preserves per-post reshares, settings and preview false/null. Mention syntax lives in text. First-comment plan eligibility and URL/URN validation stay server-side. |
| Threads | Targeting, threads, quote URL, preview hiding | Raw per-post content/media/settings/preview clearing; connection and quote lookup rules stay server-side. |
| Bluesky | Targeting, threads, quotes | Raw per-post content/media/settings and documented fields. Public guidance restricts preview-suppression convenience to LinkedIn/Threads/Substack; a schema field alone does not guarantee network behavior. |
| Mastodon | Targeting, threads, quotes | Raw per-post content/media/settings; instance eligibility and quote support stay server-side. |
| Substack Notes | Targeting, one post, restack, preview hiding | Raw media IDs, text and documented fields. Official guide allows up to six images/GIFs or one video (512 MB / 15 min), no mixed video/images or video/restack. Media-type/eligibility checks require metadata and remain server-side. No undocumented mention-lookup endpoint is invented. |
| X Article | Standalone Markdown/cover ID/null, metadata and schedule/plan through normal commands | Raw Markdown/null and cover/null. Article grammar/canonicalization, code exclusion, owned-ready static cover media and comment anchor validity remain server-side. Human rendering now includes canonical Markdown. |
| Draft metadata and timing | Title, scratchpad, tags, sharing, schedule, plan | Raw title/scratchpad null, tags empty/null, share false, platform nulls, `publish_at`/`plan_at`, and `force_overwrite_comments`. Arrays replace posts; preserve intended content/settings and exact markers. No arbitrary route escape hatch. Article inputs reject incompatible post-only flags before auth/requests. |

`publish_at="now"` starts asynchronous publication: an accepted response may still
have `status="draft"`, `publish_state="in_progress"` and null URLs. This is neither
a completed publication nor an unsent-draft failure. Poll `get` until
`publish_state="finished"`, then inspect status and platform URLs/errors. No
automatic poll/retry or additional content mutation was added. Planned drafts stay
inert until explicitly confirmed; past planned dates are not publication failures.

Public errors reviewed: 400 validation/marker errors, 401 auth, 402 monetization or
paused account, 403 access/eligibility, 404 missing resources, 409 marker conflicts,
422 schema errors, 429 rate limiting, and resolver 503. Existing `api_error`, HTTP status, 200-character top-level message, clean stdout
`user_message`, exit codes and partial-failure semantics remain. Bounded redacted
parsed diagnostics are now added at `error.upstream`, with `upstream_truncated`
when limited; missing marker IDs, malformed-marker subcodes and 422 field details
remain available beyond the old message preview.
Rate-limit response headers exist for user/social-set budgets; existing batch
throttling remains. No automatic mutation retries were added. Comment markers
must round-trip; force-overwrite is explicit, never an automatic error recovery.


## Unresolved boundaries reviewed again

- Historical October 29 MCP inventory: 24 tools mapped to the public operations,
  plus MCP-only `confirm_publish` for immediate publishing. Never send this
  MCP-only field to REST. No new MCP-only feature was verified; current
  authenticated inventory remains unavailable.
- Polls are product features, but no writable poll contract is in the unchanged
  current public schema. No guessed fields or endpoints were added.
- Webhook events/signatures/retries are documented, with no subscription
  management operations in this schema. Existing analytics/follower analytics
  and draft `content_filter` routes remain preserved compatibility surfaces with
  an unverified current public contract.
- Legacy `threadify`, auto-retweet and auto-plug request fields remain preserved
  but absent from the reviewed writable snapshot; public docs describe account
  defaults. Account permissions, quotas, network eligibility, quote lookup,
  media/platform combinations and exact server-side anchor validation remain
  authoritative. Raw payload support versus convenience flags is distinguished
  above; no all-platform live-publishing claim is made.
- No real Typefully content, scheduling, publication, uploads, settings,
  collector submissions or credentials were used. All tests use mocks/offline data.

## Monitor health and validation

The previous infrastructure failure is no longer the latest scheduled result.
[November 12 run 43259812159](https://github.com/dheeraj-shah/typefully-cli/actions/runs/43259812159)
on main completed successfully: source fetch/validation, reporting, cache save and
degraded-check steps all passed. November 9 remains a historical failed run.
No schedules, permissions, release triggers or Dependabot settings were changed.

Cloud Python 3.12 offline regression suite: 525 tests pass. Both mocked Node
collector suites: 28 tests pass. Exact CI Ruff selection and `git diff --check`
pass. Initial local test environment lacked SOCKS support because injected proxy
variables affected HTTPX construction; the offline/mocked suite passes with proxy
variables unset for that process. No live Typefully request or credential was used.
Exact final-head Python 3.9–3.13 CI status is recorded on PR #18, separately from
local verification. No merge, release, package publish or deployment occurred.
