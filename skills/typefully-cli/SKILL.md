---
name: typefully-cli
description: Use this repository's Python Typefully CLI to inspect accounts and drafts, prepare platform-specific content, and perform explicitly authorized Typefully operations. Covers JSON request input and safe validation; not the separate official JavaScript agent skill.
---

# Typefully CLI

Run `typefully --help` and the selected command's `--help` before assuming flags.
This skill describes the maintenance branch's unreleased behavior; older installed
packages may lack these commands. Do not treat repository documentation as proof
that the installed package has been upgraded.

## Access and output

Use existing authorized access and choose the intended social set with `--account`.
Do not print keys or create credentials as part of a test. `accounts --json` lists
connected sets; a configured default is not proof it is the intended destination.
`--json` controls **output**, not the request body. Most commands also offer text
output; `draft-payload` and `media-update` always emit structured JSON.

## Prepare and validate

- Use `draft`/`thread` for ordinary content and `update` for an existing draft.
- For per-post fields, explicit null/false, or full platform payloads, use
  `draft-payload create --file draft.json --validate-only`. This validates locally
  without authentication or network access. `--file -` reads stdin.
- Submitting requires removing `--validate-only` and selecting `--account`.
  Updates use `draft-payload update --draft-id ID --file update.json`.
- Platform post arrays replace content. Preserve posts/settings you intend to keep
  and exact comment markers from a normal `get`. Plain-text responses requested
  with `--exclude-comment-markers` are not safe round-trip edit input.
- `publish_at: "now"` publishes; scheduled timestamps create a publishing commitment.
  `plan_at` is dated but inert. Omit both for an unscheduled draft. Never infer
  permission to publish from permission to create or edit a draft.

## Platform and media details

- X supports reply restrictions, subscriber-only toggles and community follower
  sharing. Use the documented enum names; `null` clears a reply restriction.
- LinkedIn supports first comments (1250 characters) and reshares via URL/URN.
  `linkedin_reshare_target` is writable; `linkedin_reshare_urn` is a response field.
- Quotes use `--quote-post-url` / `--qrt` on X, Threads, Bluesky, Mastodon or Substack;
  LinkedIn uses its separate reshare target.
- `upload FILE --alt-text DESCRIPTION` sets alt text before attachment.
  `media-update ID --alt-text DESCRIPTION` or `--clear-alt-text` updates stored media.
  Previously attached drafts retain a metadata snapshot; do not silently rewrite
  drafts to refresh it.
- X Articles use a standalone `x_article` payload; creation requires Markdown content.
  Local validation cannot prove network eligibility or account-specific capabilities.

## Safe testing

There is no isolated sandbox or server dry-run documented in the reviewed sources.
Typefully's Development mode exposes IDs; its API playground is not a safety boundary.
Use mocked tests/local validation first. Live checks need authorized account access.
A strictly non-mutating check must exclude `GET /queue/schedule`, which can create
initial default settings. Never test publishing, scheduling, uploads or deletion
without authorization for those effects. If a test-draft cycle is explicitly
approved, track its returned ID, keep it unscheduled, and modify/delete only that
new test draft. A timeout is not proof a write failed; reconcile before any retry.

## Evidence and maintenance

Public API: https://typefully.com/docs/api
MCP guide: https://support.typefully.com/en/articles/13128440-typefully-mcp-server

In this repository, consult `docs/upstream-parity.md` for the complete capability
matrix and `docs/quote-parity.md` for platform flags/update semantics. Public API
coverage is not proof of all-platform behavior. The authenticated 24-tool inventory
maps to public operations but adds MCP-only `confirm_publish` for immediate
publication; never send that field to REST. Polls, webhook administration and
unverified legacy routes must not be invented from product announcements.

For repository changes, run the mocked suite and the CI lint command. Keep release
approval separate: merging, a `v*` tag, PyPI publication and Homebrew updates are
not implied by skill edits or successful tests.
