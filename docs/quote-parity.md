# Quote-post API parity (verified 2026-10-29)

`draft`, `thread`, and `update` accept `--quote-post-url` (existing alias `--qrt`)
for X, Threads, Bluesky, Mastodon, and Substack Notes. The URL chooses which
selected platform receives the quote. LinkedIn reposts are a separate feature.

```sh
typefully draft "Worth reading" --platform bluesky,linkedin \
  --quote-post-url https://bsky.app/profile/example.bsky.social/post/abc
typefully update DRAFT_ID --platform mastodon \
  --quote-post-url https://mastodon.social/@example/123
```

Only Bluesky receives the quote in the first example. The second keeps existing
text. Replacing text replaces posts, so provide the quote flag again to retain a
quote. Append preserves existing posts and attaches the quote to new content.
Substack supports one post and cannot append to an existing note.

Known hosts route to their own platform; custom publication paths `/note/c-...`
and `/p/...` route to Substack when selected. Other hosts prefer Mastodon when
selected, otherwise the sole quote-capable target. Ambiguous/mismatched targets
fail locally. The API still validates whether a particular post can be quoted.

For compatibility, X quotes continue to apply to every supplied thread post.
New quote platforms apply the quote to the first supplied post only. Metadata-only
quote changes do not rewrite unrelated platforms. No real posts are created by
the tests.

## Evidence and boundaries

- [API reference](https://typefully.com/docs/api): request schemas for XPost,
  ThreadsPost, BlueskyPost, MastodonPost and SubstackPost expose `quote_post_url`.
- [Official quote guide](https://github.com/typefully/agent-skills/blob/main/skills/typefully/references/quotes.md)
- [Official routing implementation](https://github.com/typefully/agent-skills/blob/main/skills/typefully/scripts/typefully.js):
  `classifyQuoteUrl` and `resolveQuotePlatform`.
- [Product changelog](https://typefully.com/changelog): October 9 expanded quotes.

## X and LinkedIn platform fields

The following additive options are available on `draft`, `thread`, and `update`:

| Option | API field and behavior |
| --- | --- |
| `--reply-settings following\|mentionedUsers\|subscribers\|verified\|null` | X post `reply_settings`; `null` restores the default reply audience |
| `--subscribers-only` / `--no-subscribers-only` | X post `subscribers_only`; omission does not change the field |
| `--share-with-followers` / `--no-share-with-followers` | X `settings.share_with_followers`; requires `--community` or an existing community on an update |
| `--linkedin-first-comment TEXT` | LinkedIn `settings.first_comment`, at most 1250 characters; `null` or an empty string clears it |
| `--linkedin-reshare-target URL_OR_URN` | First supplied LinkedIn post `linkedin_reshare_target`, at most 2048 characters; `null` clears it |

LinkedIn reshares accept a full post URL or canonical `urn:li:share:...`,
`urn:li:ugcPost:...`, or `urn:li:groupPost:...`. Upstream validates and normalizes
the target; the CLI enforces the documented length limit. Responses expose
`linkedin_reshare_urn`, which the CLI translates back to the writable
`linkedin_reshare_target` when preserving existing content.

```sh
typefully draft "Community update" --platform x --community 123 \
  --no-share-with-followers --reply-settings following
typefully update DRAFT_ID --platform linkedin --linkedin-first-comment "More details here"
typefully update DRAFT_ID --platform x --reply-settings null --no-subscribers-only
```

X post options apply to all supplied posts; LinkedIn reposts apply to the first
supplied post. Append applies post options only to newly appended posts and
merges settings without losing existing values. Metadata-only updates retain
text (including comment anchors), media, quotes, restrictions, and settings;
unrelated platforms are not rewritten. Text replacement continues to replace
posts wholesale. Wrong-platform options, oversized values, and community share
options without a community fail locally before the draft update request.
Media plus platform options is handled in the same content-preserving update
path. A media-only update without `--platform` retains the historical X default.

These fields are verified against `XPost`, `XSettings`, `LinkedInPost`, and
`LinkedInSettings` in the public [OpenAPI reference](https://typefully.com/docs/api),
not inferred from MCP or product UI capabilities.

Polls were announced in the product changelog, but no poll request schema was
found in the current API reference, so no API support is inferred. The MCP OAuth
connector setup is transport/auth functionality, not an API-key CLI parity gap.
