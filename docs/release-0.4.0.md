# 0.4.0 release candidate

Prepared, not published. A minor version reflects the new default-on telemetry
feature. On 2026-10-29 PyPI reported latest version 0.3.0 and no 0.4.0; the remote
Git tags had no v0.4.0. Recheck immediately before publication.

## Release contract

- Package metadata and runtime version: 0.4.0.
- Collector explicitly accepts 0.4.0 alongside the previous reviewed 0.3.0.
- First eligible interactive text invocation displays disclosure and sends nothing.
- Later eligible invocations send only version/category. Opt out with
  `TYPEFULLY_TELEMETRY=0` or `typefully config set telemetry_enabled false`.
- CI, noninteractive, JSON and quiet invocations do not send.
- Skill and privacy documentation describe these controls and infrastructure IP visibility.

## Final checks

Run the complete Python suite, CI Ruff selection, Node collector tests and
`git diff --check`. Build both sdist and wheel with `python -m build` and validate
metadata using `python -m twine check dist/typefully_cli-0.4.0*`. Install the wheel
in a clean environment and check version, help, offline payload validation and
opt-out persistence with networking blocked. Verify artifact versions, schema and
telemetry source; ensure the source distribution includes skill/privacy documents.
All telemetry tests use mocks; do not send real usage as a release check.

## Publication remains gated

Do not merge, create/push `v0.4.0`, publish to PyPI, create a GitHub release, or change
Homebrew until the owner approves those exact destinations. Pushing a `v*` tag
triggers the existing trusted PyPI publishing workflow. A PR push does not.
Homebrew is maintained separately; coordinate after the release is available,
without touching its current 0.3.0 work.

Suggested approval question: **May I merge PR #16 and publish typefully-cli 0.4.0
by pushing tag v0.4.0 (which triggers PyPI), then create the matching GitHub release?
Homebrew updates would be handled separately.**
