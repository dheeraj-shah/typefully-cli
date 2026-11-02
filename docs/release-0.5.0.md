# 0.5.0 review and deployment plan

Prepared version: **0.5.0**. This branch is not a release authorization. PyPI
currently has 0.4.0; do not replace that version, its files or its tag. The
0.4.0-only Homebrew PR #2 is held: the next tap publication should contain the
reviewed profile feature from a newly published 0.5.0 source distribution.

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

## Exact production actions requiring approval

Nothing below has been performed. The profile endpoint remains empty.

1. In personal Cloudflare account `22980d1f74f2694e0642ea3cf9f384d9`, create one
   dedicated Worker **`typefully-cli-profiles`** and one dedicated D1 database
   **`typefully-cli-profiles`**. Apply only `profile-collector/schema.sql` to that
   new database and bind it as `PROFILES`. No migration or identity table is
   added to the anonymous `daily_counts` database.
2. Enable the exact recipient
   `https://typefully-cli-profiles.dheeraj-personal-site.workers.dev`, exposing
   only `POST /v1/sync` and `POST /v1/withdraw`. No public list/read API, custom
   domain, preview URL, secret, API key or permission/security grant is added.
3. Add daily cleanup cron **`15 3 * * *` (03:15 UTC)**. Keep effective request,
   invocation, trace, persistence, Logpush and tail-consumer logging disabled.
   Review account-level exports and current D1 backups/plan before describing
   retention. The plan must remain unchanged; no upgrade or quota increase is
   authorized.
4. Review public-write abuse/quota handling before opening the route. The client
   is limited to daily bounded snapshots and the service strictly bounds and
   validates input, but it is intentionally not a proof of account ownership and
   hostile callers can fabricate public-profile submissions. No platform request
   or API credential is used server-side to verify a profile. Provider-side
   request/capacity controls, if needed, must be reviewed as exact additional
   configuration; do not add undisclosed IP tracking, new credentials or paid
   resources. This public-write control remains an activation decision.
5. Bind that fixed endpoint in `profile_sharing.py` and review its disclosure
   together with effective backend settings. Run local/mocked acceptance again
   on the activated candidate. No real-account lookup, real-profile submission
   or production acceptance request is authorized by this plan. Any such test
   needs explicit scope; use synthetic local/mocked verification by default.
6. Separately approve the source-only anonymous collector change adding exact
   `0.5.0` to `VERSIONS`, preserving its payload, exclusions, opt-outs and logging
   settings. Do not send another production analytics test request. Readback of
   code/configuration through Cloudflare management APIs can verify deployment.

## Required validation before publication

- Exact Python 3.9–3.13 CI, current Ruff selection, existing aggregate tests and
  connected-profile collector tests, plus local SQLite checks of actual SQL.
- Consent/no-consent and token secrecy, all six platforms, team/newly linked
  accounts, full pagination, all-or-none failures/bounds, no returned-URL fetch,
  daily backoff, revocation during lookup, concurrent locking, rolling expiry,
  withdrawal tombstone and delayed-upload protection.
- Wheel/sdist build and Twine metadata validation, packaged schema/profile
  module/docs/skill inclusion and source parity. Install the exact candidate in
  isolation; version/help/offline request validation and inactive privacy/status
  must work with networking blocked.
- After separately approved activation, review the final exact source tree,
  built artifact hashes and CI on that activated tree before publication.

## Publication order after final approval

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
4. With the separately reviewed tap publication approval, publish that formula
   and verify main readback/install. Do not first publish the held 0.4.0 update.

The already completed anonymous acceptance test remains exactly one known
synthetic count (`2026-11-02 / 0.4.0 / analytics`). It must be excluded from organic
analysis and left intact. No new production analytics event is part of 0.5.0 work.
