# Connected profile sharing — pre-implementation checkpoint

This supersedes the manual X-handle design. The owner now wants one explicit
opt-in to share all supported connected social profiles, with no identity lookup
or transmission when declined. The current draft code still implements the older
inactive manual flow and must not be activated or released as the new design.
No real account has been queried and no real identifiers have been transmitted.

## Verified official API contract

Reviewed the [official public API](https://typefully.com/docs/api) and its embedded
OpenAPI 3.1 schema on 2026-11-02, without authentication or account requests.

- `GET /v2/social-sets` lists accessible social sets, including individually owned
  accounts **and team accounts**. It is paginated, with a maximum page size of 50.
- `GET /v2/social-sets/{social_set_id}/` exposes connected accounts in `platforms`.
  It requires existing READ access, using the user's existing API key. No new
  OAuth scopes, credentials or Typefully write permission are needed.
- The exact documented keys are `x`, `linkedin`, `bluesky`, `threads`, `mastodon`
  and `substack`. Each value can be null when not connected.

| Platform | Public fields to allowlist | Qualification |
| --- | --- | --- |
| X | `username`, `profile_url` | Documented X handle and public profile URL |
| LinkedIn | `username`, `profile_url` | Documented vanity name and public profile URL |
| Bluesky | `username`, `profile_url` | Documented handle and public profile URL |
| Threads | `username`, `profile_url` | Documented handle and public profile URL |
| Mastodon | `username`, `profile_url` | Username excludes server suffix; public URL identifies the instance |
| Substack | `username`, `profile_url` | Both are nullable and may be unavailable |

Do not use `/me`, names, email addresses, team names, avatars, follower counts,
quotas, internal social-set/account IDs, posts or messages in the collector
payload. Social-set IDs are needed only locally to address the documented detail
GET. API credentials are sent only to the official Typefully API, never the
maintainer's collector. Raw API responses must not be logged or persisted.

## Scope decision before implementation

“All connected profiles” can mean all platforms in the selected/default social
set, or every social set visible to the API key. The latter includes team/client
accounts and must not be implied to mean only profiles owned by the person.

The recommended interpretation of **all** is every accessible social set, with
the single opt-in explicitly stating “including team or client accounts your API
key can access.” This needs owner confirmation before implementing that breadth.
If the intended scope is the current social set, say so explicitly instead; do
not silently switch between these interpretations or infer ownership from names.

## Proposed one-consent flow

1. Normal CLI usage performs no profile-sharing lookup or submission. No first-run
   prompt is added to ordinary commands. The user invokes a dedicated
   `typefully community share-profiles` command.
2. Before resolving credentials or calling Typefully, show the recipient (Dheeraj
   Shah, CLI maintainer), purpose (understand who uses the CLI), all six platform
   types, the chosen social-set/team scope, exact fields, retention and removal.
   Ask one default-no confirmation to read and share all profiles in that scope.
3. Declining or aborting performs zero identity-related API reads and zero
   collector submissions. No enabled preference or identity snapshot is saved.
   Anonymous activity counting and its existing opt-out controls stay separate.
4. After affirmative consent, use only the documented, fixed-origin READ paths.
   Fetch every page/details needed for the chosen scope, project only allowlisted
   public fields, validate types/lengths/HTTPS URLs, deduplicate repeated public
   profiles and assemble one bounded snapshot locally.
5. Submit that complete snapshot once. Do not send partial pages, truncated lists
   or raw API objects. If a required read fails, a connected profile has neither
   usable public identifier, an unknown platform appears, or the snapshot exceeds
   reviewed limits, transmit no identity snapshot and explain the limitation.
   No scraping or synthetic URL construction replaces missing API identifiers.
6. Save the random withdrawal capability in a private local receipt before the
   submission. Do not retry an uncertain submission automatically or claim it
   succeeded without confirmation. Keep the receipt for removal if uncertain.

The authenticated lookup transport must remain separate from the collector
transport. Use only `https://api.typefully.com` for Typefully authorization,
disable redirects, and paginate with local limit/offset parameters rather than
following returned `next` URLs. No client or server may fetch profile URLs, resolve
submitted hosts, follow links or download avatars. Public URLs are stored as
validated strings only, so they cannot become an SSRF fetch target. Identifier
availability and ownership are not independently verified.

## Retention, updates and deletion

Proposed storage is one complete current snapshot per withdrawal capability in a
**separate dedicated D1**, with four columns: `token_hash`, `profiles_json`,
`consent_revision` and `expires_at`. Each profile contains only platform,
documented username when available, and documented public profile URL when
available. No version/category, API/user/social-set ID or event history is stored.
The new disclosure/contract revision should be `2`; old manual-X revision `1`
must not be treated as consent for connected-account discovery.

- Expire at 90 days, exclude expired snapshots from maintainer reads, and remove
  them at the next daily cleanup (within the next 24 hours). Backups may retain
  deleted data temporarily. No public roster API or marketing/contact permission.
- No background polling or upload during normal commands. Newly linked profiles
  are not collected until another explicit full-snapshot opt-in. This keeps a
  consented snapshot from becoming a stream of command-linked identity updates.
- For an explicit refresh, replace the complete snapshot atomically and discard
  the old snapshot; no history. Preserve the original expiry unless a clearly
  disclosed fresh opt-in renews it. Never silently extend retention.
- `community withdraw-profiles` uses only the local capability, without Typefully
  credentials or profile lookup, to delete the whole remote snapshot. Remove the
  local receipt only after confirmed removal; retain it for explicit retry on an
  uncertain response. Do not collect new profile data after withdrawal. Losing
  the receipt loses automated withdrawal; expiry remains the fallback.

## Proposed release and access changes

PyPI currently publishes **0.4.0** and has no 0.5.0 release; the repository has no
`v0.5.0` tag. Propose **0.5.0** for this added opt-in feature. Never replace the
existing 0.4.0 files, tag or checksums. Homebrew's published formula is still 0.3.0;
the 0.4.0-only PR #2 is held by the owner's changed scope.

Before production work, present these exact changes for owner review:

- One new Worker, proposed name `typefully-cli-profiles`, and one dedicated D1
  database of the same name in personal account
  `22980d1f74f2694e0642ea3cf9f384d9`; no reuse of `daily_counts`.
- One daily expiry-cleanup trigger, maintainer-only D1 reads through existing
  authorization, request/log/trace/Logpush/tail logging disabled, and reviewed
  public-write abuse/quota controls. Verify the current plan; no plan upgrade,
  new credential, security grant or permission expansion is included.
- A fixed profile-recipient endpoint and revised disclosure bound together after
  the backend is reviewed/deployed. No arbitrary recipient configuration.
- If existing anonymous counting remains active for 0.5.0, a narrowly scoped
  collector redeployment adding only exact release `0.5.0` to its finite version
  allowlist, preserving its fields, exclusions, opt-outs and disabled logging.
  No further production analytics test requests are authorized.

Release order after the owner reviews the final implementation and separately
approves those destinations:

1. Test the revised consent/extraction/withdrawal path with synthetic API fixtures
   and mocked storage only, including zero reads/sends before consent, all six
   platforms, pagination, team scope, missing metadata, bounds, no URL fetches,
   no raw-field leakage, full-snapshot atomicity, retention and withdrawal.
2. Prepare 0.5.0 source/runtime/docs/changelog and the exact collector allowlist;
   run Python 3.9–3.13 CI, both collector suites, lint, package/build checks and
   isolated offline installation. Keep profile collection inactive until its
   recipient/resources are separately approved and verified.
3. Review/approve and deploy the exact backend/configuration changes, then review
   the final activated source/artifacts. No real-account or real-profile test is
   authorized; any production acceptance request needs separate explicit scope.
4. With publication approval, merge the tested release and push the exact
   `v0.5.0` tag, triggering the existing trusted PyPI publish workflow. Verify the
   published wheel/sdist and checksums.
5. Update Homebrew directly to that published 0.5.0 sdist, verify dependencies,
   native audit/install/offline tests and exact final PR head, then publish the
   separately approved tap change. Do not first publish the held 0.4.0 update.
