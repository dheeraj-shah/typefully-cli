# Typefully upstream parity baseline

Reviewed 2026-10-29 against CLI 0.2.1 / main `82fd5948`.

## Sources and limits

- [Public API reference](https://typefully.com/docs/api): endpoint and payload authority.
- [Official agent skills](https://github.com/typefully/agent-skills/tree/main/skills/typefully): usage and platform references. The executable reference is `skills/typefully/scripts/typefully.js`, not `/scripts/typefully.js`.
- [Official MCP guide](https://support.typefully.com/en/articles/13128440-typefully-mcp-server): public capability overview. The MCP endpoint requires authentication and the MCP initialization protocol; unauthenticated `tools/list` is not a valid inventory.
- [Product changelog](https://typefully.com/changelog): discovery of changes, not evidence that every product feature is exposed through the public API.

This is not a claim of exhaustive or authenticated MCP parity. Do not guess endpoints from product announcements. Existing CLI JSON payload passthrough supports documented fields before dedicated convenience flags exist.

## Monitor repair

The previous workflow treated the API root greeting as an OpenAPI schema, used a missing agent-skills path, attempted unauthenticated MCP enumeration, and swallowed fetch failures. It could therefore report no changes despite incomplete coverage.

The replacement monitors validated public API documentation, official agent source, public MCP documentation, and the changelog. It ignores scripts/styles in HTML to reduce dynamic-build noise. It does **not** label documentation as an OpenAPI schema, enumerate private MCP tools, require a new credential, or claim a successful fetch proves semantic feature parity. The old npm probe is removed: the official skill source is the maintained reference, and a package version was not established as an authoritative API contract.

First valid reads establish a baseline. Changes or failures create a deduplicated issue. Failures preserve the last good source baseline and mark the workflow failed. Baselines advance only after reporting succeeds, so an issue-delivery failure does not silently lose a change. The existing Monday/Thursday cron and `issues: write` / `contents: read` permissions are unchanged; this remains issue-only automation.

Run public-source validation without creating an issue:

```sh
python3 scripts/monitor.py --cache-dir /tmp/typefully-monitor-check
```

This performs public GET requests only. Tests use injected fake responses and never call Typefully accounts.

## Maintenance coordination

Dependabot's existing five open Actions-upgrade PRs (#9, #11, #12, #13, #14 at review time) are not duplicated here. CI is pinned to Ubuntu 22.04 to keep the advertised Python 3.9–3.13 matrix working rather than silently dropping Python 3.9 after `ubuntu-latest` moved to Ubuntu 26.04.

Publishing remains unchanged and is triggered by `v*` tags. Maintenance branches and draft PRs must not create tags, publish packages, merge, or mutate real Typefully content as tests.
