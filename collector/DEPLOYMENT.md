# Deployment verification — 2026-10-29

Owner approved dedicated personal Cloudflare Worker + D1 creation on the confirmed
Workers/D1 Free plan; no plan change, credentials, or security grants were made.

- Endpoint: `https://typefully-cli-telemetry.dheeraj-personal-site.workers.dev/v1/count`
- Worker: `typefully-cli-telemetry`
- Account: `22980d1f74f2694e0642ea3cf9f384d9` (Dheeraj Shah)
- D1: `typefully-cli-telemetry`, ID `1c795c09-fb39-41bf-bf9d-a4f7deae6c9c`
- Worker version: `e251b178-c17f-44d1-99e5-ca1006ad1067`
- D1 read replication: disabled

Uploaded `worker.mjs` with only its default fetch export. The API upload response
confirmed `observability.enabled=false`, log/invocation-log/trace enabled flags
false, both log/trace persistence flags false, `logpush=false`, and empty tail
consumers. Subsequent settings readback confirmed the dedicated D1 binding,
`logpush=false` and empty tail consumers; disabled observability was omitted from
that read response. Account Logpush jobs list was empty. The workers.dev route was
read back enabled with preview URLs disabled.

Checks against the deployed endpoint used no real usage:

- GET `/v1/count` returned 405 with an empty body.
- POST of the rejected synthetic dimensions `synthetic-test` / `synthetic-test`
  returned 400 with an empty body.
- D1 schema readback showed only `day`, `version`, `category`, `count`.
- D1 count after both checks: zero rows. No production-dimension count was sent.
- Local Node tests: 7 passed. SQLite schema/upsert checked locally.

This verifies the rejection path and deployed configuration, not a production
accepted-event end-to-end write. Accepted payload/database behavior is tested
locally with a mock D1 binding. Cloudflare infrastructure still receives IP and
transport metadata; application configuration and account Logpush checks do not
verify all provider-internal security retention. No claim of full anonymity.

The example Wrangler configuration remains intentionally inactive. An operator
must copy it and explicitly supply the above binding/approved route before future
deployment. Do not upgrade the Free plan automatically; quota exhaustion should
leave telemetry best-effort, not change CLI behavior or authorize charges.

## Prepared 0.4.0 candidate update — 12:20 UTC

The existing collector was redeployed with only the reviewed version allowlist
expanded from `0.3.0` to `0.3.0` and `0.4.0`; the CLI candidate is not published.
Downloaded deployed source confirmed both exact versions. Local mock tests accept
both and reject `0.4.0-rc.1`, `0.4.1`, and `0.5.0`.

Upload again confirmed all observability/logging/tracing and persistence flags
false, Logpush false, and no tail consumers. Settings readback confirmed the same
D1 binding and no Logpush/tails; account Logpush jobs remain empty. Route remains
enabled and previews disabled. A rejected synthetic POST returned 400 with zero
response bytes; a subsequent D1 count confirmed zero rows. No accepted production
payload was sent. No resources, paid plan
changes, credentials, or grants were added by this update.
