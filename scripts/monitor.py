"""Read-only public-source monitoring; publish a report before advancing the baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

# Public documentation is deliberately not presented as an authenticated MCP inventory.
SOURCES = {
    "api-docs": ("https://typefully.com/docs/api", "html", "Typefully"),
    "agent-skills": (
        "https://raw.githubusercontent.com/typefully/agent-skills/main/skills/typefully/scripts/typefully.js",
        "text",
        "api.typefully.com",
    ),
    "mcp-docs": (
        "https://support.typefully.com/en/articles/13128440-typefully-mcp-server",
        "html",
        "Typefully",
    ),
    "changelog": ("https://typefully.com/changelog", "html", "Typefully"),
}
MAX_BYTES = 12 * 1024 * 1024


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def fetch(url):
    request = Request(url, headers={"User-Agent": "typefully-cli-upstream-monitor/1"})
    with urlopen(request, timeout=45) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("source exceeds size limit")
    return raw.decode("utf-8")


def normalize(raw, kind, marker):
    if kind == "html":
        if "<html" not in raw.lower():
            raise ValueError("expected an HTML documentation page")
        parser = VisibleText()
        parser.feed(raw)
        raw = " ".join(parser.parts)
    value = re.sub(r"\s+", " ", raw).strip()
    if len(value) < 100 or marker.lower() not in value.lower():
        raise ValueError("empty or unexpected source content")
    return value


def collect(cache, fetcher=fetch, sources=SOURCES):
    cache.mkdir(parents=True, exist_ok=True)
    baseline_file = cache / "baseline-v2.json"
    baseline = json.loads(baseline_file.read_text()) if baseline_file.exists() else {}
    pending = dict(baseline)
    changes, failures, initialized = [], [], []
    for name, (url, kind, marker) in sources.items():
        try:
            content = normalize(fetcher(url), kind, marker)
            digest = hashlib.sha256(content.encode()).hexdigest()
            previous = baseline.get(name)
            pending[name] = {"url": url, "sha256": digest}
            if previous is None:
                initialized.append(name)
            elif previous != pending[name]:
                changes.append(name)
        except (OSError, ValueError) as error:
            # Retain the last valid baseline and never call a failed fetch "unchanged".
            failures.append({"source": name, "error": type(error).__name__})
    result = {
        "changed": changes,
        "failed": failures,
        "initialized": initialized,
        "status": "degraded" if failures else "changed" if changes else "ok",
    }
    report = ["Typefully public-source monitoring report", ""]
    for name in changes:
        report.append(f"- Changed: {name}: {sources[name][0]}")
    for failure in failures:
        name = failure["source"]
        report.append(f"- Fetch/validation failed: {name} ({failure['error']}): {sources[name][0]}")
    if initialized:
        report.append("- Initialized validated baselines: " + ", ".join(initialized))
    report += [
        "",
        "This checks public sources, not authenticated MCP tools/list or full API parity.",
        "Review source changes against the CLI before implementing updates.",
    ]
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "changed": {name: pending[name] for name in changes},
                "failed": failures,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:16]
    result["fingerprint"] = fingerprint
    result["title"] = f"Monitor: Typefully upstream {result['status']} ({fingerprint})"
    result["report_needed"] = bool(changes or failures)
    (cache / "pending-v2.json").write_text(json.dumps(pending, indent=2) + "\n")
    (cache / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    (cache / "report.md").write_text("\n".join(report) + "\n")
    return result


def commit(cache):
    # Called only after issue creation/deduplication succeeds.
    pending = cache / "pending-v2.json"
    pending.replace(cache / "baseline-v2.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=Path(".monitor-cache"))
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if args.commit:
        commit(args.cache_dir)
    else:
        result = collect(args.cache_dir)
        print(json.dumps(result))


if __name__ == "__main__":
    main()
