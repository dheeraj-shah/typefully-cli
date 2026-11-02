# Optional ongoing connected-profile sharing

Version 0.5.0 is an unpublished review candidate. Profile sharing is off by
default, `PROFILE_ENDPOINT` is empty, and no profile service/database/cron has
been created. No identity collection can run until the reviewed fixed recipient
is activated in a separately approved build. Published 0.4.0 is unchanged.

## One consent, every accessible account

`typefully community privacy` shows the full disclosure without accessing an
account. `typefully community share-profiles` asks one explicit default-no
confirmation **before resolving credentials or reading profiles**. The consent
covers every social set visible to the API key used by the CLI, including managed
team/client accounts and profiles connected later. The person must confirm they
have permission to share those managed/client profiles. There is no manual handle
entry or per-platform opt-in, and ordinary commands never prompt for consent.

Declining or aborting saves no enabled consent and performs no identity lookup or
collector request. This refers to profile sharing; anonymous activity counting
retains its separate disclosure, exclusions and opt-out controls.

The recipient is Dheeraj Shah, the CLI maintainer. The sole purpose is context
about who uses the CLI. It is not marketing consent, a public directory, proof of
ownership or a reliable unique-user count. No automatic messages or contact occur.

## Exact data and official API support

The [official API](https://typefully.com/docs/api), reviewed 2026-11-02, documents
READ access to `/v2/social-sets` and `/v2/social-sets/{social_set_id}/`. The list
includes personal and team accounts. No new API scope, credential or Typefully
write permission is needed. `/me`, content, drafts and messages are not read for
sharing. API credentials go only to the official API, never the maintainer.

The allowlist is `platforms.x`, `linkedin`, `bluesky`, `threads`, `mastodon` and
`substack`. Only each account's documented `username` and public `profile_url` are
projected; no raw API object is submitted. Names, emails, avatars, follower counts,
team metadata, internal IDs, quotas and tokens are discarded. Social-set IDs are
used only locally to address detail reads. URLs are stored as strings, never
fetched or resolved. No scraping or invented profile URL fills missing data.

Substack's username and URL may be null. If one valid public identifier is
available it is used; if both are absent, sharing aborts without a partial upload.
Missing/unknown platform metadata, failed reads and bounds violations also abort
the complete snapshot. The CLI does not silently truncate or claim unsupported
platforms were shared. Upstream reads are not a transactional instant snapshot;
changes made during or after a lookup are included on a later eligible sync.

One collector request has these fields:

| Field | Purpose |
| --- | --- |
| `profiles` | Full current deduplicated array: platform, public username and/or URL |
| `consent_revision` | Exact ongoing/team-account disclosure revision `3` |
| `snapshot_at` | Current seconds timestamp, validated within five minutes to reject stale uploads; not stored separately |
| `withdrawal_token` | Random 256-bit removal capability; raw value is not stored by the service |

Before any identity lookup, `POST /v1/register` sends only the random withdrawal
token, consent revision and current `requested_at` timestamp to reserve a bounded
empty record. Failed admission causes no profile lookup. Empty reservations
expire after one hour and idempotent replays do not extend them. Every due cycle
confirms admission first, including recovery after inactivity. `POST /v1/sync`
can only update an already admitted, unexpired record; it cannot insert a fresh
token. There is no registration request before explicit consent.

The source recipient is fixed, not user-configurable. Existing manual-X revision
`1` and the one-time snapshot proposal do not authorize ongoing collection. No
old manual-entry receipt is migrated into consent for this feature.

## Ongoing sync and limits

After opt-in, each successful eligible interactive command can perform a due sync
at most once per 24 hours. It includes all then-accessible accounts and newly
connected profiles, and removes disconnected profiles by replacing the whole
snapshot. The API key already resolved for the user's command is reused in memory
and then discarded from command context; automatic sync does not prompt 1Password
a second time. The receipt stores no key or profile list.

There is no daemon, timer process, background upload, command log or event queue.
CI, noninteractive/redirected use, JSON output, quiet/debug runs, config,
completions, community commands and help/version do not automatically sync.
`community sync-profiles` can perform a due interactive sync but cannot bypass the
24-hour limit, which the server also enforces per admitted token. Failures also
back off for a day. Each later attempt fetches a new
current snapshot; it does not replay old captured data. Profile-sync failures do
not change the triggering command's output or exit status.

Bounds: 100 accessible social sets, 600 distinct profile records, 64 KiB encoded
snapshot, 1 MiB per API response, and a ten-second lookup budget checked across
all pages/response chunks. Per-network-operation timeouts are at most two seconds;
admission and final submission add their own timeouts. These are best-effort transport bounds,
not a hard real-time scheduling guarantee. Over-limit accounts send no partial
data. API pagination uses fixed paths and local offsets, never returned URLs.
Both transports disable redirects and environment/proxy credentials. The server
limits request bodies to 128 KiB and independently validates the finite contract.

## Server-side request and storage ceilings

These are strict shared D1 checks, not per-process or approximate per-location
counters. One bounded `profile_budget` row holds only the current UTC day/minute
and aggregate request/admission counts, without per-event or per-user budget
rows. SQL constraints/triggers check admission and capacity atomically.

| Guard | Threshold | Exhaustion behavior |
| --- | --- | --- |
| Registration/sync and unknown-token withdrawal requests | 30 per UTC minute and 2,000 per UTC day, globally combined | 429, conservative `Retry-After: 86400`; no new admission/snapshot |
| New token records | 50 per UTC day | 429; failed client admission prevents identity lookup |
| Total records, including pending and revoked | 1,000 | 503 for new admission; existing-record sync/deletion remains possible |
| Profile JSON | 64 KiB per record, at most 600 profiles | Rejected; SQL also enforces size/array bounds |
| Successful updates per admitted token | At least 24 hours apart | 429; snapshot and expiry unchanged |
| Admission/withdrawal bodies | 256 bytes | 400; no token record allocated |
| Request-body read time | 5 seconds | 408 and cancel the stalled stream; no token record allocated |

At most 62.5 MiB of profile JSON can be stored (1,000 × 64 KiB), plus bounded
metadata/budget/index and SQLite overhead. This is a logical data ceiling, not a
promise about physical database pages or provider backups. Expired records are
reclaimed before admission and by daily cleanup. Expiry does not refund the daily
admission quota. Rejected requests cannot grow counters past their ceilings, and
older clock windows cannot reset the shared counters backwards.

Known-token withdrawal bypasses request/admission/capacity quotas. It only clears
an existing record and never inserts one. Repeating completed withdrawal does
not write again or extend its expiry. Unknown tokens allocate no record and use
the shared request gate: 204/no-op while budget remains, 429 when exhausted. Each
request still needs one small indexed existence check.

These controls bound stored data and admitted work; an attacker can still consume
the shared admission budget or provider HTTP/read quotas. They do not establish
profile ownership. Known deletion bypasses this application's quotas, but a
Cloudflare/D1 outage or exhausted account allowance can still delay it. Local
revocation remains effective and the receipt permits retry. No automatic
capacity, plan or credential increase occurs.

## Retention means rolling 90 days

Each profile record stores only `token_hash`, `profiles_json`, `consent_revision`,
internal lifecycle `status` (pending/active/revoked), and `expires_at`. The
singleton operational budget row is described above. Every successful sync atomically replaces
the prior snapshot and sets expiry to 90 days after that sync. **Active use can
retain the current profiles indefinitely until withdrawal.** Old snapshots are
not kept as history. After 90 days without successful sync, the snapshot expires;
maintainer reads exclude it, and the next successful daily cleanup removes it,
normally within 24 hours. Failed/quota-blocked cleanup needs operator attention.
Consent remains local until revoked, so later eligible use can obtain admission for a
fresh current snapshot after inactivity.

There is no join to command counts, release version, social-set ID, machine ID,
email or API user. Maintainer reads use existing authorized D1 access with:

```sql
SELECT profiles_json FROM profile_snapshots
WHERE profiles_json IS NOT NULL AND expires_at > unixepoch();
```

No public read/roster endpoint exists. No exports are made by the implementation;
any later authorized export must honor the same removal/retention obligations.
No application request, IP, user-agent, log/trace, Logpush or tail-consumer data is
recorded. Hosting infrastructure still receives IP and connection metadata. This
is identified profile data, not anonymous analytics. Provider backups may retain
deleted data temporarily; do not promise instant backup erasure.

## Revocation and deletion

`typefully community status` reads only local state and never prints the token.
The private `profile-sharing.json` receipt records recipient, consent, token and
coarse sync status/times, with Unix mode 0600. Keep it for removal. Losing the
receipt loses automated removal capability; remote expiry after inactivity is
the fallback.

`typefully community withdraw-profiles` first writes a local stop marker, before
locking or networking. Future lookups/submissions stop immediately. A lookup
already running checks the stop marker before submission. Interprocess locking
prevents concurrent successful sync/deletion races. If a sync is already in
flight, local revocation remains effective and the command asks the person to
retry remote deletion once it finishes.

Removal uses only the capability and needs no Typefully credentials or account
lookup. Confirmed withdrawal replaces an existing admitted record's data with a **hash-only
tombstone** for 90 days, preventing delayed requests from restoring it. No profile
identifier remains in that tombstone. Five-minute request freshness also rejects
very old in-flight payloads after the tombstone expires. Unknown tokens cannot
create tombstones. An initial admission finishing after uncertain withdrawal can
leave only a bounded empty one-hour reservation; the stopped client performs no
profile lookup or upload. Successful removal clears
the local receipt; failures retain it for explicit deletion retry while sync stays
disabled. A new opt-in after removal generates a new capability. The source never
automatically re-enables consent or silently sends a token to a new recipient.

## Review and activation

All tests use synthetic fixtures and mocked transport/storage. No real profiles
have been read or sent. The inactive template has no account, D1 binding, public
route or cron. See [the exact proposed deployment/release plan](release-0.5.0.md)
before approving backend resources, endpoint activation, publication or Homebrew.
