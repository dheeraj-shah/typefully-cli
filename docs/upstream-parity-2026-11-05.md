# Typefully capability review: 2026-11-05

Reviewed release 0.5.0, main `b2d57487bf043e70587438ea079c5ae75818330f`.
Main's exact-head CI [41934821263](https://github.com/dheeraj-shah/typefully-cli/actions/runs/41934821263)
succeeded. PR #15 is merged; this review uses a new dated maintenance branch.
No open PR existed at the initial check. No release, package, Homebrew, collector
deployment, dependency, schedule or permissions change is part of this review.

## Source baseline and verification limits

| Authority | Current observation | Limits |
| --- | --- | --- |
| [Public API](https://typefully.com/docs/api) | Read live through connected web tools on November 5. An independent allowed cloud-browser check used the official Download OpenAPI Document control: 319,957 bytes, OpenAPI 3.1, API 2.0.0, 24 HTTP operations at 16 paths. All 22 bundled request components equal the current same-named components, with zero differences. Additional queue/comment schema constraints were read directly from the saved source. | Direct cloud-shell fetch is blocked by the environment's host policy. Library materialization also failed at download; the browser-verified comparison and Library text reads supply schema evidence, not local readable-byte verification in this executor. |
| [Official agent source](https://github.com/typefully/agent-skills/blob/main/skills/typefully/scripts/typefully.js) | Downloaded current source and its linked comments, quotes, X, LinkedIn and X Article guides. Script SHA-256 `105d36f89ed38b75e898f731b51d1d618386d932a0b88344c510e82cae571308`. | Reviewed as API usage evidence, not executed, installed or used to find credentials. Its defaults and command spelling are not this Python CLI's contract. |
| [MCP guide](https://support.typefully.com/en/articles/13128440-typefully-mcp-server) | Current guide describes draft lifecycle, multi-platform posts, queue/published views, media, tags and connected accounts. OAuth / Streamable HTTP at `https://mcp.typefully.com/mcp`; headless Bearer auth remains documented. | Endpoint inventory could not be retrieved through public web access. No credentials, initialization, authenticated `tools/list` or tool invocation were used. Public `/health` retrieval reports `ok` but was cached, and proves no inventory or account capability. |
| [Changelog](https://typefully.com/changelog) | Latest visible entry is October 28 (Substack videos/mentions); reviewed polls, planned posts, Claude/MCP and other visible entries. | Product announcements are not writable API schemas. Direct shell fetch is blocked. |

The current full schema SHA-256 is
`d130baba5ac3265880cf6ecc6d98889252bc2b00371f45f91277132c57a33da6`.
Canonical compact sorted JSON for its 22 selected request components hashes to
`f8a54276896cedd5a79e332f0261711b282b45ac6d75e3e664000b2ea924ce14`.
The request component bodies are unchanged from October 29; `request-schemas.json`
now records the November 5 retrieval and full-source hash. Local `--validate-only`
reports that metadata date. The saved public source is preserved in the private
maintenance evidence rather than duplicated in this repository.

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
| POST `S/tags` | `tag-create`, automatic tag creation | New local 1..32-character name check; automatic names are all checked before tag requests. Server still owns slug generation, uniqueness and eligibility. |
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
| Draft metadata and timing | Title, scratchpad, tags, sharing, schedule, plan | Raw title/scratchpad null, tags empty/null, share false, platform nulls, `publish_at`/`plan_at`, and `force_overwrite_comments`. Arrays replace posts; preserve intended content/settings and exact markers. No arbitrary route escape hatch. |

`publish_at="now"` starts asynchronous publication: an accepted response may still
have `status="draft"`, `publish_state="in_progress"` and null URLs. This is neither
a completed publication nor an unsent-draft failure. Poll `get` until
`publish_state="finished"`, then inspect status and platform URLs/errors. No
automatic poll/retry or additional content mutation was added. Planned drafts stay
inert until explicitly confirmed; past planned dates are not publication failures.

Public errors reviewed: 400 validation/marker errors, 401 auth, 402 monetization or
paused account, 403 access/eligibility, 404 missing resources, 409 marker conflicts,
422 schema errors, 429 rate limiting, and resolver 503. Existing `api_error` with
HTTP status, stderr details, exit codes and partial-failure semantics remain.
Rate-limit response headers exist for user/social-set budgets; existing batch
throttling remains. No automatic mutation retries were added. Comment markers
must round-trip; force-overwrite is explicit, never an automatic error recovery.

## MCP, unsupported and unverified boundaries

- The separately authorized October 29 inventory in [the historical baseline](upstream-parity.md)
  listed 24 tools mapping to the operation matrix, with MCP-only `confirm_publish`
  default false. It is historical evidence, not a new authenticated inventory.
  Never send that MCP-only field to REST. No other MCP-only feature is currently verified.
- OAuth is recommended by the current guide. Plain Bearer auth is documented for
  headless MCP clients; legacy query-key URLs still work but migration to plain
  URL/OAuth is recommended. This maintenance does not create or change auth.
- Polls are announced in the product, but no writable public poll field was
  verified in the accessible documentation/snapshot. No guessed API feature was added.
- Webhook events, signatures and retry descriptions are public; no public webhook
  subscription-management operations were found. The CLI is not a webhook receiver.
- Existing analytics/follower analytics and `content_filter` remain compatibility
  surfaces with an unverified current public contract. Legacy `threadify`,
  auto-retweet and auto-plug request convenience fields are preserved but absent
  from the reviewed writable snapshot; the public docs describe account defaults.
- No verified missing public HTTP operation remains in this matrix. Raw support
  versus dedicated flags is distinguished above; absence of an extra convenience
  flag alone is not a missing API capability. The current request snapshot was
  verified against the downloaded public schema; current authenticated MCP
  inventory and all-account runtime behavior remain unverified.

## Monitor health and repair

Latest scheduled run [41494356894](https://github.com/dheeraj-shah/typefully-cli/actions/runs/41494356894),
November 2, job `125445276250`, succeeded. Its logs show a cache miss, four validated
source initializations, no failed sources and a successful cache save. This is a
healthy fresh baseline, not proof of no changes since previous runs.

The old API digest removed every script/style, making embedded-schema-only changes
invisible. A separate `api-schema` baseline now extracts embedded OpenAPI JSON
(including escaped/chunked Next flight strings) without executing scripts. It
hashes the canonical contract alongside the unchanged visible-docs baseline;
generated examples and unrelated script nonces do not affect that contract digest.
Fields actually named `example`/`examples` are retained. Missing, malformed or
conflicting schemas cause degraded monitoring and preserve the last good digest.
Both API views share one fetch. Transactional report-before-baseline behavior,
issue deduplication and failure reporting remain covered by offline tests.

The new schema entry initializes on its first successful read without discarding
existing baselines. Tests cover direct JSON, escaped JSON, split flight chunks,
schema-only changes, ordering/nonces/examples, missing schemas and retained state.
The embedding parser could not be exercised on current raw HTML in this cloud
environment; extraction failure will be visible rather than called unchanged.
Monday/Thursday cron, workflow permissions, weekly Actions Dependabot and tag-only
publishing triggers are unchanged. No scheduled workflow was dispatched here.

All maintenance validation is offline/mocked. No real content, media uploads,
account settings, authenticated Typefully calls or collector submissions were used.
The historical one-off live draft smoke test was separately authorized and was not
repeated. Merge, release, publishing and deployment require separate authorization.

Local validation: 448 Python tests, exact CI Ruff selection, Python 3.9 syntax
parsing/compilation, whitespace checks, 28 Node collector tests and wheel schema/module
inclusion checks passed. Remote CI must be assessed for the final PR head; local
Python 3.12 results alone are not a five-version CI claim.
