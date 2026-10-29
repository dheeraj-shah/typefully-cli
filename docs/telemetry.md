# Usage telemetry

## Current status

The maintainer-owned collector is deployed at
`https://typefully-cli-telemetry.dheeraj-personal-site.workers.dev/v1/count`.
This unreleased branch is configured to use it, subject to the notice and opt-out
rules below. Existing published 0.3.0 installations are unchanged. A package
release still requires separate approval. There is no third-party analytics SDK.
See [deployment verification](../collector/DEPLOYMENT.md).

## What an activated build measures

A request contains only the released CLI version and an allowlisted command
category: account, drafts, publishing, media, tags, analytics, comments, or queue.
It does not contain command arguments, post text, API keys, account information,
errors, hostnames, installation IDs, or device identifiers. It measures command
activity, **not unique users**, installations, or successful API operations.

The collector increments a daily aggregate count for version/category. It does
not store individual events or application-level IP/user-agent logs. Aggregate rows
older than 90 days are removed on the next accepted request; if traffic stops,
they remain until another request or operator cleanup. Backups may retain deleted
aggregates temporarily. Network and
hosting infrastructure necessarily receive source IPs and connection metadata;
this is not a promise of full anonymity or zero infrastructure retention.

## Notice and opt-out

Before any sending can begin, an interactive invocation displays a notice naming
the collector and opt-out controls. That invocation sends nothing. Only a later
eligible invocation can send. A local marker records that notice for that endpoint;
it is not an identifier and is never uploaded. The first notice does not rewrite
your API-key configuration.

Disable before running any other command:

```sh
export TYPEFULLY_TELEMETRY=0
# Or persist the preference:
typefully config set telemetry_enabled false
```

Opt-out takes precedence over the notice marker. Config and completion commands,
help/version, CI, noninteractive runs, and structured/quiet output do not send.
Telemetry failures must not fail the user's command. There is no retry queue,
background process, or retrospective upload of skipped commands.

## Maintainer activation checklist

1. Obtain approval for the specific collector recipient and hosting resource changes.
2. Verify the account's Workers/D1 plan and spending behavior; do not assume free
   allowances imply zero possible charges on an existing paid account.
3. Review the collector deployment guide, disable invocation logs, traces, logpush,
   and tail consumers, and review infrastructure-level retention separately.
4. Validate the collector with synthetic payloads only after testing authorization;
   all repository tests use mocks and must not send actual CLI usage.
5. Configure the fixed HTTPS endpoint in source. Do not accept a user-controlled
   endpoint or reuse the authenticated Typefully API client.
6. Review the disclosure against the deployed recipient, fields, and retention.
7. Obtain separate approval before merging or publishing a release.

Counts are approximate and can be inflated by clients or bots. Do not add IP-based
fingerprints or persistent IDs to deduplicate them. See [collector](../collector/)
for the source and deployment prerequisites.
