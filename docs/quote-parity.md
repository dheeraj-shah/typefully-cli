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

The API also documents X `reply_settings` and `subscribers_only`, plus LinkedIn
`settings.first_comment`; dedicated CLI flags remain future work. Polls were
announced in the product changelog, but no poll request schema was found in the
current API reference, so no API support is inferred. The MCP OAuth connector
setup is transport/auth functionality, not an API-key CLI parity gap.
