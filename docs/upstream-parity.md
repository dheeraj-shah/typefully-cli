# Typefully upstream parity baseline

Reviewed 2026-10-29 against CLI 0.2.1 / main `82fd5948`.

## Sources and limits

- [Public API reference](https://typefully.com/docs/api): endpoint and payload authority.
- [Official agent skills](https://github.com/typefully/agent-skills/tree/main/skills/typefully): usage and platform references. The executable reference is `skills/typefully/scripts/typefully.js`, not `/scripts/typefully.js`.
- [Official MCP guide](https://support.typefully.com/en/articles/13128440-typefully-mcp-server): public capability overview. The MCP endpoint requires authentication and the MCP initialization protocol; unauthenticated `tools/list` is not a valid inventory.
- [Product changelog](https://typefully.com/changelog): discovery of changes, not evidence that every product feature is exposed through the public API.

This is not a claim of exhaustive or authenticated MCP parity. Do not guess endpoints from product announcements. The previous CLI `--json` flag controlled output only; it was not request-body passthrough. This maintenance adds an explicit `draft-payload` command, described below.

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


## Complete public API capability matrix (2026-10-29 snapshot)

The API page embeds an OpenAPI 3.1 specification: **24 HTTP operations across 16 paths**. The following maps every operation, not just newly changed features. Paths below are relative to `/v2`; `S` denotes `/social-sets/{social_set_id}` and `D` denotes `S/drafts/{draft_id}`.

| Public API operation(s) | CLI surface | Evidence / qualification |
| --- | --- | --- |
| GET `/me` | `me` | Existing |
| GET `/social-sets` | `accounts`, account resolution | Now follows all 50-item pages instead of truncating at 50 |
| GET `S/` | `account` | Existing detail command |
| GET / POST `S/drafts` | `drafts`; `draft`, `thread`, `batch`, `draft-payload create` | Repeated `--tag` filters supported; JSON input covers per-platform/per-post fields |
| GET / PATCH / DELETE `D` | `get`; `update`, `publish`, `schedule`, `plan`, `draft-payload update`; `delete` | Explicit JSON null/false/empty arrays survive unchanged; server content/comment rules still apply |
| POST `S/media/upload` | `upload --alt-text` | Alt text up to 1000 characters, including empty text |
| GET / PATCH `S/media/{media_id}` | `media-status`; **new `media-update`** | Patch supports replacement and explicit null clearing |
| GET / POST `S/tags` | `tags`, `tag-create` | Existing |
| GET / PUT `S/queue/schedule` | `queue-schedule get/set` | Existing |
| GET `S/queue` | `queue` | Existing |
| GET `S/linkedin/organizations/resolve` | `linkedin-resolve` | Existing |
| GET / POST `D/comment-threads` | `comments list/create` | Existing; pagination bounds checked |
| POST `D/comment-threads/{thread}/comments` | `comments reply` | Existing |
| POST `D/comment-threads/{thread}/resolve` | `comments resolve` | Existing |
| PATCH / DELETE `D/comment-threads/{thread}/comments/{comment}` | `comments update/delete --comment-id` | Existing |
| DELETE `D/comment-threads/{thread}` | `comments delete` without comment ID | Existing |

This is **operation coverage**, not proof that every account-dependent behavior has been exercised against the live service. All maintenance tests are offline/mocked.

### Request fields and platform behavior

- New dedicated create/thread/update flags: X `reply_settings` (`following`, `mentionedUsers`, `subscribers`, `verified`, or `null`), `subscribers_only` including false; community `share_with_followers` including false; LinkedIn `first_comment` (1250 characters, null/empty clears) and `linkedin_reshare_target` (URL or URN, 2048 characters, null clears).
- Response `linkedin_reshare_urn` is converted to writable `linkedin_reshare_target` when updating copied posts. Other platform posts, settings and comment-marked text are preserved for metadata-only updates.
- Quotes: X, Threads, Bluesky, Mastodon and Substack supported; LinkedIn uses its separate reshare field, not `quote_post_url`.
- The explicit request-input command covers the reviewed schema for all **seven** platform keys: X, LinkedIn, Threads, Bluesky, Mastodon, Substack, and X Article. It preserves per-post distinctions, settings, media, tags, scheduling/planning, null-clearing, false toggles, and `force_overwrite_comments` on update. It does not automatically remove comment markers or overwrite comments.
- `src/typefully_cli/request-schemas.json` is the API page's transitive create/update schema snapshot, with source and retrieval date. The dependency-free validator implements only that snapshot's finite keyword vocabulary; regression tests reject unrecognized future schema keywords. Type, required/unknown fields, conditional fields, lengths, enums and timezone-aware date-time shape are checked locally. Server-side eligibility, URL/URN validity, supported media/platform combinations, scheduling limits and account permissions remain authoritative.
- Media alt text is snapshotted when attached to a draft. Updating stored media does not silently rewrite already-attached drafts. Intentionally resend draft content to refresh an attachment after updating its media.
- Existing `--json` remains an **output** switch. New request input uses `--file`, including stdin (`-`). It is explicit, not an arbitrary HTTP escape hatch.

```sh
# Pure local validation: no account, token or network required.
typefully draft-payload create --file draft.json --validate-only
# These commands mutate your chosen account only when explicitly invoked:
typefully draft-payload create --file draft.json --account my-account
typefully draft-payload update --draft-id 123 --file update.json --account my-account
typefully media-update MEDIA_ID --alt-text "Descriptive image text" --account my-account
typefully media-update MEDIA_ID --clear-alt-text --account my-account
```

Update payloads containing platform post arrays replace content, rather than magically merging missing posts. Include content/settings to retain. `publish_at: "now"` is a real publication request; `plan_at` is inert planning. Local validation cannot certify that a request will succeed on every social network.

### Remaining boundaries, not fabricated parity

1. **Authenticated MCP inventory unverified.** The public MCP guide describes capabilities but is not a complete `tools/list` result. OAuth-backed inventory and schemas would be needed to establish exact MCP-only gaps; no new authorization or credentials were created in this work.
2. **Polls:** product announcements are not a writable public API contract. No poll request schema was found in this snapshot, so no guessed endpoint or flags were added.
3. **Analytics / follower analytics:** existing CLI routes are preserved, but absent from this particular 24-operation public snapshot. Their current contract is unverified here, not automatically declared supported or removed.
4. **Webhook management:** a webhook event payload schema exists, but no public management operations in the snapshot. Do not infer create/delete subscription endpoints.
5. **Legacy `threadify` / auto-retweet / auto-plug convenience fields:** preserved for compatibility, but not in the reviewed draft request schema. New `draft-payload` rejects undocumented fields instead of pretending they are supported.
6. **Defaults and syntax:** the Python CLI retains its established account/default-platform resolution instead of copying the official agent script's interface. Equivalent supported capabilities do not require identical flags or defaults.
7. **Product/media rollout differences:** product announcements (for example Substack video) can outpace platform guidance. Do not guarantee an account/platform media combination solely from a changelog item.

Weekly maintenance must re-check this entire matrix, implement verified gaps even if they predate the latest diff, update the request snapshot/validator together, and leave unsupported or inaccessible capabilities explicitly marked. A failed source read is degraded monitoring, not evidence of no change.
