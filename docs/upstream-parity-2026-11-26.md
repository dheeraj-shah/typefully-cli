# Typefully capability review: 2026-11-26

Base: release 0.5.1, main `657806084f4983b9f0e9caa4dc50e88a456000a4`.
Previous complete review: [November 19](upstream-parity-2026-11-19.md).

## Fresh evidence and limits

- The [official public API reference](https://typefully.com/docs/api) now lists
  29 operations across 19 paths, including five linked quote operations.
  Extracted the official embedded OpenAPI 3.1 / API 2.0 schema and checked
  every operation, parameters, request references and response status sets.
  All 22 bundled request components match upstream after transport
  normalization. The canonical full-schema SHA-256 is
  `869675a7fe5eb550db1574b192e107c7774f36b1f206e12d3faf59d564cf7f2c`.
  This contract digest is not the hash of the downloadable file.
- The [MCP guide](https://support.typefully.com/en/articles/13128440-typefully-mcp-server)
  still documents OAuth and drafts, accounts, queues, tags and media. No current
  authenticated inventory was available: an unauthenticated protocol initialization
  on November 26 returned HTTP 401. The historical 24-tool inventory does not establish whether
  current MCP exposes engagements.
- The [product changelog](https://typefully.com/changelog) announces scheduled
  quotes (including LinkedIn reposts), Substack videos/mentions and earlier
  polls. The scheduled quote contract is verified in REST. The bundled draft
  fields already support Substack media IDs and text; no mention resolver or
  poll write field is documented. Do not infer a new endpoint from the UI.
- The official [agent CLI](https://github.com/typefully/agent-skills/blob/main/skills/typefully/scripts/typefully.js)
  still documents ordinary quotes via published post URLs. These are distinct
  from engagement drafts following a parent. No new auth or live account calls.

## Complete operation matrix

Paths are relative to `/v2`; `S` is `/social-sets/{social_set_id}` and `D` is
`S/drafts/{draft_id}`. Implemented/tested means offline regression coverage and
reviewed routing; it does not mean live all-account or all-platform execution.

| Public operation(s) | Dedicated CLI / raw request surface | Current review and tests |
| --- | --- | --- |
| GET `/me` | `me` | Current user and API key label; existing structured output/error tests. |
| GET `/social-sets` | `accounts`, account resolution | Auto-paginates 50-item pages; cache/pagination tests. Dedicated output retains the established list shape rather than the API pagination envelope. |
| GET `S/` | `account-detail` | All documented platform objects pass through JSON. Human output includes `publishing_quota` used/remaining/reset fields, including `unlimited`. |
| GET `S/drafts` | `drafts`, `recent` | Limit 1..50, offset >=0, repeated tag slugs, all six statuses and eight sort orders. Existing local enum validation; JSON preserves the API envelope; human/CSV nullable-preview and date rendering is regression-tested. `recent` filters published dates locally and paginates date ranges. |
| POST `S/drafts` | `draft`, `thread`, `batch`; `draft-payload create` | All seven platform keys, metadata, scheduling/planning and sharing covered by the reviewed snapshot. Raw input preserves per-post fields/null/false; offline validation and transport tests. |
| GET `D` | `get`, `open` | Comment markers retained by default; display-only exclusion flag. Human output now shows X Article Markdown, all platform publication URLs and `publish_state`. |
| PATCH `D` | `update`, `publish`, `schedule`, `plan`; `draft-payload update` | Raw input preserves explicit null/false/empty arrays and force-overwrite choice. Null selected-platform append/media handling is regression-tested. Nullable platform dictionaries and null article placeholders now validate without internal errors. Async publication progress is displayed, with manual `get` polling guidance. |
| DELETE `D` | `delete` | Existing single/multiple delete and partial-failure contract; no maintenance content deletion. |
| POST `S/media/upload` | `upload` | Filename sanitization now respects 255 characters. Alt text <=1000. S3 uses raw PUT bytes without Typefully auth or Content-Type headers. Mocked processing now stops on `failed` and preserves the reason; timeout is a distinct structured error with a polling ID. |
| GET `S/media/{media_id}` | `media-status` | Existing UUID validation; human output displays `error_reason`, `alt_text`, and `media_urls.original`, preserving the old top-level URL fallback. JSON remains unchanged. |
| PATCH `S/media/{media_id}` | `media-update` | UUID validation, <=1000-character replacement, explicit null clearing. Already-attached drafts retain their snapshot until content is explicitly resent. |
| GET `S/tags` | `tags` | Limit/offset controls. Dedicated JSON retains the established results-list shape. Automatic tag discovery paginates. |
| POST `S/tags` | `tag-create`, automatic tag creation | Existing exact slugs take priority over display names. Name lookup paginates; auto-creation consumes the server-returned slug. Aliases deduplicate in draft/thread/update/batch payloads, and failures stop before draft writes. New names remain 1..32 characters; slugs are never guessed. |
| GET `S/queue/schedule` | `queue-schedule get` | May initialize missing defaults on the server, despite its read-style name. Never used as a non-mutating account check. |
| PUT `S/queue/schedule` | `queue-schedule set --rules` | Full replacement, including `[]`. Existing local array/object, unknown-field, integer hour/minute, non-empty weekday list and duplicate day/time checks before auth. No timezone-update field is invented. |
| GET `S/queue` | `queue --start-date ... --end-date ...` | Required valid dates, ordered range and >62-day rejection. Account timezone governs dates; exact boundary/account rules remain server-authoritative. Human output now reads `days[].items[].at`, shows free slots and distinguishes inert planned drafts from scheduled drafts; legacy shapes still render. |
| GET `S/linkedin/organizations/resolve` | `linkedin-resolve URL` | Company/school URL to organization metadata and mention syntax. Resolver-only, not general search. Existing routing/output coverage. |
| GET `D/comment-threads` | `comments list` | Limit/offset, seven platform filters and unresolved/resolved/all statuses. Existing local enum checks; unresolved remains default. |
| POST `D/comment-threads` | `comments create` | Post index or standalone article anchor; selected text 1..50000, body 1..10000, occurrence 0..10000. Exact substring, LinkedIn atomic mention and article overlap rules remain server-side. |
| POST `D/comment-threads/{thread}/comments` | `comments reply` | UUID/body validation and mocked request coverage. |
| POST `D/comment-threads/{thread}/resolve` | `comments resolve` | UUID validation; server controls authorship/access and anchor removal. |
| PATCH `D/comment-threads/{thread}/comments/{comment}` | `comments update` | Both UUIDs and body validated; authorship remains server-side. |
| DELETE `D/comment-threads/{thread}/comments/{comment}` | `comments delete ID THREAD COMMENT` | Both UUIDs validated. Deleting the root comment can delete its whole thread. |
| DELETE `D/comment-threads/{thread}` | `comments delete ID THREAD` | UUID validated; whole-thread deletion removes anchors. |
| GET `D/engagements` | `engagements list` | Parent READ access; preserves the documented `results` list envelope (no pagination parameters documented). |
| POST `D/engagements` | `engagements create` | Parent READ and quote-account PUBLISH. Required integer quote draft ID, seconds 0..31536000, and kind `quote`. Attaches or reparents an existing unpublished draft. Published parent schedules it from now rather than the parent's original publication date. |
| GET `D/parent` | `engagements parent` | Quote-account READ; returns parent status, date, social set and first-post previews even without access to the parent's social set. |
| PATCH `D/engagements/{engagement_id}` | `engagements update` | Quote-account PUBLISH; new offset, same range. Parent must not have published. |
| DELETE `D/engagements/{engagement_id}` | `engagements detach` | Quote-account PUBLISH. Keeps the draft, planned for a future date or undated otherwise; 204 is reported as a detached ID. |

The three comment-body commands previously collided with shared output `--text`,
preventing valid body parsing. They now keep `--text BODY` and expose `--human`
for the output override; `--json` and the success/error envelopes are unchanged.
Tests cover valid body parsing, boundary lengths, article anchors, rejection before
auth, and unique CLI help options.

## Writable fields and platforms

The November 18 official changelog confirms up to 20 mixed media attachments
for an X post, including through the API and MCP. The checked REST schemas
cap all post media-ID arrays at 20; stricter platform or media-combination
rules remain server-side. Raw payloads already enforce the schema cap.
Dedicated draft, thread and update commands now reject oversized input before
auth or tag creation. Batch skips oversized entries (and their tag creation)
while retaining the partial-result contract for other entries.

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
The client now exposes documented, validated user and social-set budget
headers on HTTP 429 through the optional `error.rate_limit` object. Each
present scope has any available `limit`, `remaining`, and `reset` (Unix
seconds); a bounded dotted resource identifier is optional for social sets.
Unknown headers and malformed values are omitted. Success output, existing
batch throttling, and exit codes remain unchanged. No retry is performed. Comment markers
must round-trip; force-overwrite is explicit, never an automatic error recovery.


## Unresolved boundaries reviewed again

- Historical October 29 MCP inventory: 24 tools mapped to the public operations,
  plus MCP-only `confirm_publish` for immediate publishing. Never send this
  MCP-only field to REST. No new MCP-only feature was verified; current
  authenticated inventory remains unavailable.
- Polls are product features, but no writable poll contract is in the
  current public reference. No guessed fields or endpoints were added.
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


## Engagement behavior

While following a parent, an engagement cannot be independently scheduled or published.
The server resolves cross-account permissions and platform eligibility. Threads stays
within the same social set. A failed parent platform post cannot be quoted on that
platform. Deleting a parent detaches rather than deletes its engagements. Draft response
fields `parent_draft_id`, `parent_social_set_id`, `parent_offset_seconds`,
`engagement_kind` and `follows_parent` pass through the CLI's existing JSON output.
They are not added as writable draft fields. PATCH and DELETE take the documented
`engagement_id` path parameter; response examples expose `draft_id` and do not explicitly
state whether those IDs differ. Offline tests check the request shape, not live ID resolution. Ordinary `--quote-post-url` is unchanged.

## Monitor and tests

The cloud monitor fetched and validated all five configured public sources
successfully in a new temporary cache. That fresh-cache run establishes
source health, not that upstream was unchanged. The latest scheduled
[November 23 monitor](https://github.com/dheeraj-shah/typefully-cli/actions/runs/45252655206)
succeeded on main. No monitor schedules, permissions, dependencies or release
triggers were changed. The new regression tests use an in-process HTTP
transport; no real Typefully mutations, authentication or media uploads.
