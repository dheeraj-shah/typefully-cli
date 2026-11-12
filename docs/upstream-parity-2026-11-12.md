# Typefully capability review: 2026-11-12

Reviewed main `b2d57487bf043e70587438ea079c5ae75818330f` (0.5.0) and the existing
[draft PR #18](https://github.com/dheeraj-shah/typefully-cli/pull/18), starting at
`26a8273281c72763d2ae1c17952734459ca7da89`. PR #15 is merged. PR #18 is reused;
no duplicate PR, merge, release, deployment or permission/schedule change is part
of this run.

## Fresh source evidence

- [Public API](https://typefully.com/docs/api): the complete official Download
  OpenAPI Document control was independently used in an allowed cloud browser on
  November 12, without authentication. It is byte-identical to November 5:
  319,957 bytes, SHA-256
  `d130baba5ac3265880cf6ecc6d98889252bc2b00371f45f91277132c57a33da6`,
  OpenAPI 3.1.0 / API 2.0.0, **24 HTTP operations at 16 paths**. All 22 bundled
  request components again equal the same-named current components, with zero
  differences. Only retrieval metadata advances to November 12.
- [Official agent source](https://github.com/typefully/agent-skills/blob/main/skills/typefully/scripts/typefully.js)
  and its linked comments, quotes, X, LinkedIn and X Article guides were read
  fresh through the GitHub connection. They remain usage evidence, not commands
  executed with account credentials. In particular, article post-only flag
  prohibitions and tag-slug requirements are checked against actual Python
  behavior rather than inferred from endpoint coverage.
- [MCP guide](https://support.typefully.com/en/articles/13128440-typefully-mcp-server):
  current lifecycle, media, tags, account and queue capabilities were reviewed.
  It still recommends OAuth / Streamable HTTP and documents headless Bearer auth;
  legacy query-key URLs remain compatible with migration to plain URL/OAuth
  recommended. Public access to the MCP endpoint failed. No authentication or
  tool invocation was attempted, so the October 29 inventory remains historical.
- [Changelog](https://typefully.com/changelog): latest visible entry remains
  October 28 (Substack videos/mentions). Poll and other product announcements
  are not treated as new writable public fields or endpoints.

The full matrix below was rechecked, including its known unresolved boundaries;
schema equality alone is not a full parity claim. The selected cloud executor
failed provisioning, so repository edits use the connected GitHub API and offline
validation runs in the existing PR's Actions workflow. No local test execution is
claimed for this run.

## Implemented carried-over behavior gaps

1. **Names versus tag slugs.** A new `resolve_tag_slugs` helper maps each requested
   name or exact existing slug to the authoritative server slug, including tags
   beyond the first page and opaque/non-predictable creation results. The four
   CLI writers deduplicate aliases and send slugs. Resolution failures abort
   before any draft create/PATCH; batch preflights the full input before its first
   draft. Auto-creation remains supported. Existing `ensure_tags` retains its
   documented warning-list return contract.
2. **Useful API diagnostics.** Existing top-level error fields and
   `APIError.user_message` are retained. Optional `error.upstream` carries
   parsed, bounded, redacted diagnostics, rather than losing every detail after
   the first 200 characters. Marker missing IDs, malformed-marker subcodes and
   422 validation locations/messages remain available. Non-JSON fallback stays
   unchanged. No automatic force-overwrite or mutation retry was added.
3. **Article option rejection.** Explicit article create/update inputs reject
   post-only text/file/media, replies/quotes/communities, disclosure and preview
   flags, append/threadify and incompatible platform flags before auth or
   requests. Pure payload building also rejects ignored article post options.
   Valid Markdown, cover-only/null updates and ordinary metadata remain supported.

## Complete operation matrix

Paths are relative to `/v2`; `S` is `/social-sets/{social_set_id}` and `D` is
`S/drafts/{draft_id}`. Implemented/tested means offline regression coverage and
reviewed routing; it does not mean live all-account or all-platform execution.

| Public operation(s) | Dedicated CLI / raw request surface | Current review and tests |
| --- | --- | --- |
| GET `/me` | `me` | Current user and API key label; existing structured output/error tests. |
| GET `/social-sets` | `accounts`, account resolution | Auto-paginates 50-item pages; cache/pagination tests. Dedicated output retains the established list shape rather than the API pagination envelope. |
| GET `S/` | `account-detail` | All documented platform objects pass through JSON. Human output now includes `publishing_quota` used/remaining/reset fields, including `unlimited`. |
| GET `S/drafts` | `drafts`, `recent` | Limit 1..50, offset >=0, repeated tag slugs, all six statuses and eight sort orders. New local enum validation; JSON preserves the API envelope. `recent` filters published dates locally and paginates date ranges. |
| POST `S/drafts` | `draft`, `thread`, `batch`; `draft-payload create` | All seven platform keys, metadata, scheduling/planning and sharing covered by the reviewed snapshot. Raw input preserves per-post fields/null/false; offline validation and transport tests. |
| GET `D` | `get`, `open` | Comment markers retained by default; display-only exclusion flag. Human output now shows X Article Markdown, all platform publication URLs and `publish_state`. |
| PATCH `D` | `update`, `publish`, `schedule`, `plan`; `draft-payload update` | Raw input preserves explicit null/false/empty arrays and force-overwrite choice. Nullable platform dictionaries and null article placeholders now validate without internal errors. Async publication progress is displayed, with manual `get` polling guidance. |
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

## Monitor health

Latest scheduled run [42672465820](https://github.com/dheeraj-shah/typefully-cli/actions/runs/42672465820)
failed November 9 before creating a job. The public run annotation states
"Internal server error" with correlation ID
`2e58ec06-2ef6-4ca6-a516-4c7aa17202d4`; job lists are empty. This is GitHub
infrastructure failure, not evidence that the monitor script ran or fetched a
source unsuccessfully.

One bounded failed-run rerun request was attempted. GitHub refused it with
HTTP 403, "This workflow run cannot be retried"; the run remains attempt 1,
completed/failure. No retry executed, and no workflow settings were changed.

Prior run [42061203109](https://github.com/dheeraj-shah/typefully-cli/actions/runs/42061203109),
November 5 on the same main commit, succeeded: all four sources fetched, cache
restored from the prior run, API docs marked changed, no source failures. It
reported/deduplicated [issue #19](https://github.com/dheeraj-shah/typefully-cli/issues/19)
and saved the baseline. It was not a fresh-cache "no changes" result.

Main still lacks PR #18's unmerged schema-monitor improvements. The draft keeps
separate visible-text and embedded-contract baselines, reference-ID normalization,
failure visibility and transactional baseline updates. The November 5 browser-DOM
check of embedded components remains historical evidence; the November 12 fresh
full-schema download is separate evidence. Direct raw-HTTP extraction was not
reverified from the unavailable executor. Failed/unavailable source reads are
degraded verification, never evidence of no changes.

Monday/Thursday monitor cron, weekly Actions Dependabot, permissions and tag-only
publishing triggers remain unchanged. The infrastructure failure remains unresolved;
no successful rerun or live monitor repair is claimed.

## Validation

Regression coverage includes name/capitalization/exact-slug collisions,
pagination, opaque creation slugs, deduplication, and failures across all four
writers; long marker/422 diagnostics, bounded/redacted errors and non-JSON fallback;
and incompatible article flags before requests on both create/update paths.
The existing CI runs all offline Python tests and exact Ruff selection on
Python 3.9–3.13, plus both mocked Node collector suites. Final-head CI evidence is
recorded in PR #18 and the maintenance report; the prior green run is not used as
a claim that a new head passed.
