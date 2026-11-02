# Production verification — 2026-11-02

The owner approved this exact staged activation and 0.5.0 PyPI/Homebrew release,
including the thresholds, rolling retention and backup/deletion limitations.
The owner explicitly confirmed Workers Free. No plan, credential, permission,
paid service or account setting was changed.

## Resources and deployed source

- Personal account: `22980d1f74f2694e0642ea3cf9f384d9`.
- Worker: `typefully-cli-profiles`, active version
  `4118a429-9344-49e6-a149-f1dba6968fcb` (100%).
- Recipient: `https://typefully-cli-profiles.dheeraj-personal-site.workers.dev`.
- Dedicated D1: `typefully-cli-profiles`,
  `0dbc2643-1afc-468f-9e8f-62b3d76570e0`, binding `PROFILES` only.
- D1 read replication: disabled; primary region WNAM.
- Cleanup schedule: `15 3 * * *` (03:15 UTC daily), read back from the API.
- workers.dev enabled, preview URLs disabled. No custom domain/read API.

Both `worker.mjs` and imported `storage.mjs` were uploaded as JavaScript modules.
Management-API downloads matched both source files byte for byte. The actual
`fetch` and `scheduled` handlers were present. This verifies cleanup source and
schedule, not a completed cron run: activation was after today's scheduled time,
so the first scheduled run is 2026-11-03. No manual production event was invoked.

The complete `schema.sql` was applied only to this new database. SQLite metadata
readback matched both tables, expiry index and both admission triggers. It
enforces 30 guarded requests/minute, 2,000/day, 50 admissions/day, 1,000 total
records, and 64 KiB/600 profiles per snapshot. Source readback also verifies daily
sync, one-hour pending reservations and quota-independent known-token withdrawal.
At 09:15 UTC, the profile table had zero records and the singleton budget retained
its untouched seed (`day=-1`, `minute=-1`, all counts zero). No token, synthetic
profile, real profile or acceptance request was submitted.

## Effective logging and retention

The upload response explicitly confirmed observability disabled; log, invocation
log and trace enabled flags false; both log/trace persistence flags false;
`logpush=false`; and empty tail consumers. Settings readback independently
confirmed the dedicated binding, no Logpush and no tails. That read omits disabled
observability fields, so the explicit deployed-upload response is also retained
as evidence. Account Logpush jobs were empty on the final management read.
The implementation has no export, URL-fetch or platform-credential functionality.
Provider-internal transport/security retention is outside these application flags.

Profiles expire 90 days after the last successful sync; active use can retain
the current snapshot indefinitely. Daily cleanup removes expired data. Withdrawal
removes live profiles and retains only a blocking token hash/status for 90 days.
On the confirmed Free plan, the documented D1 Time Travel window is seven days;
deleted data can remain in recovery backups during that window. The new database's
Time Travel bookmark read succeeded. Retention is plan-defined, not a separately
configurable value exposed by these D1 APIs. No operator export was created.

Provider outage or shared quota exhaustion can delay cleanup or remote deletion.
Local withdrawal still stops sync and retains the receipt for deletion retry.
Do not increase quotas, upgrade the plan or change retention automatically.

## Account capacity and verification limits

Preflight found three existing databases totaling 237,568 bytes, five Workers and
one existing cron. With this service the account uses four of ten Free database
slots and two of five cron slots. Reported Workers analytics from 00:00–09:13 UTC
showed 975 requests and no errors. D1 analytics reported 11,054 rows read and 436
written before schema creation. These are observed analytics, subject to provider
sampling/delay, not a reservation of future allowance. Existing workloads share
Free limits (100,000 Worker requests/day; five million D1 reads and 100,000 writes/day).
The 62.5 MiB logical JSON ceiling fits the 500 MB Free database limit with ample
headroom, but physical pages/indexes/backups are additional. New database size
after schema creation was 24,576 bytes.

The existing OAuth connection cannot read billing subscriptions. Plan evidence
is the owner's explicit Free confirmation; no extra billing access was requested.
An initial analytics rate-limit response cleared after the requested wait.
No production HTTP test was used to verify availability or accepted persistence.
The full Python/Node suites exercise consent, identity projection, quota abuse,
retention and deletion with synthetic fixtures, mock transports and local SQLite.

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/),
[D1 pricing](https://developers.cloudflare.com/d1/platform/pricing/) and
[D1 limits and recovery windows](https://developers.cloudflare.com/d1/platform/limits/).
