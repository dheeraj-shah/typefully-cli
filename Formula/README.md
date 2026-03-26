# Homebrew Formula for typefully-cli

This directory contains the Homebrew formula, staged here before moving to a dedicated tap repo.

## Setup the tap

1. Create a repo named `homebrew-tap` under `dheeraj-shah` (or your preferred GitHub org).
2. Copy `Formula/typefully-cli.rb` into that repo at `Formula/typefully-cli.rb`.
3. Push to GitHub.

## Install

```bash
brew tap dheeraj-shah/tap
brew install typefully-cli
```

## Filling in resource hashes

The formula has `TODO` placeholders for sha256 hashes. To fill them in:

```bash
pip install homebrew-pypi-poet
poet typefully-cli
```

Paste the output over the existing resource blocks. Then validate:

```bash
brew audit --new typefully-cli
brew install --build-from-source typefully-cli
brew test typefully-cli
```

## Updating to a new version

1. Bump the `url` in the formula to the new PyPI tarball URL.
2. Update the top-level `sha256` with the new tarball hash.
3. Re-run `poet typefully-cli` to check if any dependency versions changed. Update resource blocks as needed.
4. Run `brew audit` and `brew test` to verify.
