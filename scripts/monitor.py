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
    "api-schema": ("https://typefully.com/docs/api", "openapi", "Typefully"),
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


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.current = []

    def handle_endtag(self, tag):
        if tag == "script" and self.current is not None:
            self.parts.append("".join(self.current))
            self.current = None

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)


def json_fragments(text):
    """Read JSON literals embedded in JavaScript without evaluating any code."""
    decoder = json.JSONDecoder()
    position = 0
    while position < len(text):
        match = re.search(r'[\[{"]', text[position:])
        if match is None:
            break
        position += match.start()
        try:
            value, end = decoder.raw_decode(text, position)
        except ValueError:
            position += 1
        else:
            yield value
            position = end


def extract_openapi(raw):
    """Extract a direct JSON spec or an escaped Next.js flight payload.

    A changed/missing embedding fails visibly instead of silently reverting to
    visible text, which cannot observe schema-only changes.
    """
    parser = Scripts()
    parser.feed(raw)
    specs, flight = [], []

    def visit(value, depth=0):
        if depth > 100:
            raise ValueError("embedded schema exceeds nesting limit")
        if isinstance(value, dict):
            if "openapi" in value:
                if (
                    not isinstance(value["openapi"], str)
                    or not value["openapi"].startswith("3.")
                    or not isinstance(value.get("paths"), dict)
                    or not value["paths"]
                    or not isinstance(value.get("components", {}).get("schemas"), dict)
                    or "Typefully" not in value.get("info", {}).get("title", "")
                ):
                    raise ValueError("unexpected embedded OpenAPI document")
                specs.append(value)
            else:
                for child in value.values():
                    visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)
        elif isinstance(value, str) and '"openapi"' in value:
            for child in json_fragments(value):
                if child != value:
                    visit(child, depth + 1)

    for script in parser.parts:
        for value in json_fragments(script):
            # Next flight chunks can divide one JSON document across scripts.
            if isinstance(value, list) and len(value) == 2 and value[0] == 1:
                if isinstance(value[1], str):
                    flight.append(value[1])
            visit(value)
    if flight:
        for value in json_fragments("".join(flight)):
            visit(value)
    if not specs:
        raise ValueError("embedded OpenAPI document missing or unrecognized")
    unique = {json.dumps(spec, sort_keys=True) for spec in specs}
    if len(unique) != 1:
        raise ValueError("conflicting embedded OpenAPI documents")
    return specs[0]


def schema_contract(value, named=False):
    """Ignore generated examples, preserving fields literally named 'example'."""
    if isinstance(value, dict):
        return {
            key: schema_contract(
                child,
                key
                in (
                    "properties",
                    "schemas",
                    "paths",
                    "responses",
                    "headers",
                    "webhooks",
                    "securitySchemes",
                    "content",
                    "$defs",
                    "patternProperties",
                ),
            )
            for key, child in value.items()
            if named or key not in ("example", "examples")
        }
    if isinstance(value, list):
        return [schema_contract(child) for child in value]
    return value


def fetch(url):
    request = Request(url, headers={"User-Agent": "typefully-cli-upstream-monitor/1"})
    with urlopen(request, timeout=45) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("source exceeds size limit")
    return raw.decode("utf-8")


def normalize(raw, kind, marker):
    if kind == "openapi":
        return json.dumps(
            schema_contract(extract_openapi(raw)), sort_keys=True, separators=(",", ":")
        )
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
    fetched = {}
    for name, (url, kind, marker) in sources.items():
        try:
            if url not in fetched:
                try:
                    fetched[url] = fetcher(url)
                except (OSError, ValueError) as error:
                    fetched[url] = error
            if isinstance(fetched[url], Exception):
                raise fetched[url]
            content = normalize(fetched[url], kind, marker)
            digest = hashlib.sha256(content.encode()).hexdigest()
            previous = baseline.get(name)
            pending[name] = {"url": url, "sha256": digest}
            if previous is None:
                initialized.append(name)
            elif previous != pending[name]:
                changes.append(name)
        except (OSError, ValueError, RecursionError, TypeError, AttributeError) as error:
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
