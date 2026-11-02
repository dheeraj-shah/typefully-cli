# 0.5.0 deployment and release plan

Version: **0.5.0**. The owner approved the exact staged activation and
PyPI/Homebrew publication on 2026-11-02, subject to final configuration, artifact
and CI checks. Do not replace 0.4.0, its files or its tag. The held 0.4.0-only
Homebrew update is superseded by the verified published 0.5.0 source distribution.
See [profile deployment evidence](../profile-collector/DEPLOYMENT.md) and
[aggregate collector evidence](../collector/DEPLOYMENT.md).

## Concrete behavior for review

One explicit default-no opt-in covers all accessible accounts, including team
and client profiles and profiles added later. The person confirms permission to
share those managed profiles. Only documented public platform/username/profile
URL fields go to Dheeraj Shah for usage context. Decline means zero additional
identity lookup/submission. Later eligible interactive use syncs at most daily;
there is no daemon. Anonymous activity telemetry stays separate.

The current complete snapshot replaces prior data. Expiry is **rolling**: 90 days
after the last accepted sync, so ongoing active use can retain current profiles
indefinitely. Withdrawal stops sync locally before networking, removes profile
data, and retains only a random token hash for 90 days to block delayed uploads.
No posts/messages/emails/names/avatars/internal account IDs or API credentials are
submitted. See [full data, scope, limits and removal](profile-sharing.md).

## Approved production scope

This scope authorizes the following resources and configuration only. It does
not authorize real-profile queries/submissions or production acceptance events.

1. In personal Cloudflare account `22980d1f74f2694e0642ea3cf9f384d9`, create one
   dedicated Worker **`typefully-cli-profiles`** and one dedicated D1 database
   **`typefully-cli-profiles`**. Apply only `profile-collector/schema.sql` to that
   new database and bind it as `PROFILES`. No migration or identity table is
   added to the anonymous `daily_counts` database.
2. Enable the exact recipient
   `https://typefully-cli-profiles.dheeraj-personal-site.workers.dev`, exposing
   only `POST /v1/register`, `POST /v1/sync` and `POST /v1/withdraw`. No public list/read API, custom
   domain, preview URL, secret, API key or permission/security grant is added.
3. Add daily cleanup cron **`15 3 * * *` (03:15 UTC)**. Keep effective request,
   invocation, trace, persistence, Logpush and tail-consumer logging disabled.
   Review account-level exports and current D1 backups/plan before describing
   retention. The owner explicitly confirmed Workers Free; its documented D1
   recovery window is seven days. The plan must remain unchanged; no upgrade or
   quota increase is authorized.
4. Review the implemented strict D1 ceilings: 30 guarded requests per UTC minute,
   2,000 per UTC day, 50 new records per UTC day, and 1,000 total records including
   pending/active/revoked. Each profile JSON is capped at 64 KiB (at most 62.5 MiB
   total logical JSON), each admitted token updates at most daily, and empty
   reservations expire after one hour. All limits apply across Worker instances.
   Known-token deletion bypasses those quotas; unknown withdrawal allocates
   nothing and shares the request budget. No rate-limit binding, KV, Durable
   Object, new credential or permission is required. These conservative
   traffic/capacity thresholds were approved by the owner. Changing them requires review
   of both source and schema. Exhaustion deliberately rejects admission/uploads
   rather than increasing capacity or billing. The service still does not prove
   ownership and attackers can consume shared admission or provider quotas.
5. Bind that fixed endpoint in `profile_sharing.py` and review its disclosure
   together with effective backend settings. Run local/mocked acceptance again
   on the activated candidate. No real-account lookup, real-profile submission
   or production acceptance request is authorized by this plan. Any such test
   needs explicit scope; use synthetic local/mocked verification by default.
6. Deploy only the approved source-only anonymous collector change adding exact
   `0.5.0` to `VERSIONS`, preserving its payload, exclusions, opt-outs and logging
   settings. Do not send another production analytics test request. Readback of
   code/configuration through Cloudflare management APIs can verify deployment.

## Required validation before publication

### Account, effective configuration and backup checks before activation

Do these read-only checks against the exact personal account before creating or
opening the service; no result from the earlier aggregate collector proves the
new service's current plan/settings:

- Confirm current Workers/D1 plan, shared daily request/read/write allowances,
  remaining database/account storage, database slots and cron slots. Check other
  workloads sharing those allowances. The design uses only Workers + D1; no paid
  add-on is necessary. The owner's explicit Free-plan confirmation is the plan
  evidence when billing-subscription reads are unavailable to the existing OAuth
  connection; do not expand its permissions to inspect billing.
  A Paid plan or insufficient remaining allowance requires a new cost/capacity
  decision; never upgrade or change grants automatically. Application request
  gates do not prevent incoming HTTP invocations from counting at Cloudflare.
- Verify the new database ID/binding and disabled read replication, apply the
  complete schema including the singleton budget and triggers, and verify its
  exact checks/ceilings before routing traffic. Bundle both `worker.mjs` and
  imported `storage.mjs`; do not upload the entry module alone.
- Verify effective deployed version metadata and settings disable observability,
  invocation logs, log/trace persistence, Logpush, tail consumers and preview
  URLs. Review account-level exports/destinations as well as source configuration.
  A template or a settings response omitting disabled fields is not full proof.
- Verify actual D1 Time Travel/backup retention for the current plan and any
  operator exports. Current documented recovery windows are 7 days on Free and
  30 on Paid; confirm the applicable configuration before the disclosure is
  finalized. Removal/expiry does not imply instant erasure from backups. Keep the
  daily cleanup's failure/status checks available without logging profiles.

Sources checked while preparing this plan:
[Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/),
[D1 limits/backup windows](https://developers.cloudflare.com/d1/platform/limits/),
[D1 statements and transactions](https://developers.cloudflare.com/d1/worker-api/d1-database/).
Provider quota exhaustion/outage can still delay legitimate remote deletion;
the client must stay locally revoked and keep its receipt for retry.

### Candidate checks

- Exact Python 3.9–3.13 CI, current Ruff selection, existing aggregate tests and
  connected-profile collector tests, plus local SQLite checks of actual SQL.
- Consent/no-consent and token secrecy, all six platforms, team/newly linked
  accounts, full pagination, all-or-none failures/bounds, no returned-URL fetch,
  daily backoff, revocation during lookup, concurrent locking, rolling expiry,
  withdrawal tombstone, delayed-upload protection, fresh-token/withdrawal abuse,
  strict minute/day/new-admission/storage limits, concurrent admissions, exhausted
  quota deletion and bounded schema constraints.
- Wheel/sdist build and Twine metadata validation, packaged schema/profile
  module/docs/skill inclusion and source parity. Install the exact candidate in
  isolation; version/help/offline request validation and inactive privacy/status
  must work with networking blocked.
- After separately approved activation, review the final exact source tree,
  built artifact hashes and CI on that activated tree before publication.

## Approved publication order

1. Merge the exact tested final release source. Push exact tag **`v0.5.0`** at
   that commit, triggering the existing trusted PyPI publish workflow. Do not
   approve a PR on the user's behalf or bypass required review.
2. Confirm successful publication, download official PyPI wheel and sdist, and
   verify their hashes/source/version. The inactive artifacts built during draft
   review are not the eventual activated release artifacts.
3. Update Homebrew to the actual **published 0.5.0 sdist URL/checksum**. Revalidate
   resource constraints/checksums, native strict audit/source installation,
   version/help/offline tests with identity/analytics traffic blocked, and the
   exact final tap PR head. No new formula is advertised before PyPI exists.
4. Under the approved 0.5.0 tap publication scope, publish that formula
   and verify main readback/install. Do not first publish the held 0.4.0 update.

The already completed anonymous acceptance test remains exactly one known
synthetic count (`2026-11-02 / 0.4.0 / analytics`). It must be excluded from organic
analysis and left intact. No new production analytics event is part of 0.5.0 work.
