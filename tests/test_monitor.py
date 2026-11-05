"""Offline regression tests for fail-visible, transactional monitoring."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "monitor", Path(__file__).parents[1] / "scripts/monitor.py"
)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
SOURCES = {"docs": ("https://example.invalid/docs", "html", "Typefully")}


def page(text="API docs"):
    return "<html><body>Typefully " + text * 30 + "</body></html>"


def test_baseline_only_advances_after_commit(tmp_path):
    result = monitor.collect(tmp_path, lambda _: page(), SOURCES)
    assert result["initialized"] == ["docs"]
    assert not result["report_needed"]
    assert not (tmp_path / "baseline-v2.json").exists()
    monitor.commit(tmp_path)
    assert monitor.collect(tmp_path, lambda _: page(), SOURCES)["status"] == "ok"
    assert monitor.collect(tmp_path, lambda _: page("new fields"), SOURCES)["changed"] == ["docs"]
    # Failed issue delivery must not advance the old baseline.
    assert monitor.collect(tmp_path, lambda _: page("new fields"), SOURCES)["changed"] == ["docs"]
    monitor.commit(tmp_path)
    assert monitor.collect(tmp_path, lambda _: page("new fields"), SOURCES)["status"] == "ok"


def test_failure_preserves_good_baseline_and_reports_degraded(tmp_path):
    monitor.collect(tmp_path, lambda _: page(), SOURCES)
    monitor.commit(tmp_path)
    old = json.loads((tmp_path / "baseline-v2.json").read_text())

    def fail(_):
        raise OSError("secret should not be copied into report")

    result = monitor.collect(tmp_path, fail, SOURCES)
    assert result["status"] == "degraded"
    assert result["report_needed"]
    assert result["failed"] == [{"source": "docs", "error": "OSError"}]
    assert "secret" not in (tmp_path / "report.md").read_text()
    monitor.commit(tmp_path)
    assert json.loads((tmp_path / "baseline-v2.json").read_text()) == old
    assert monitor.collect(tmp_path, fail, SOURCES)["title"] == result["title"]


@pytest.mark.parametrize("raw", ['"👋"', "", "<html>error</html>"])
def test_reject_unexpected_content(raw):
    with pytest.raises(ValueError):
        monitor.normalize(raw, "html", "Typefully")


def test_html_ignores_script_churn():
    a = page() + '<script>nonce="123"</script>'
    b = page() + '<script>nonce="456"</script>'
    assert monitor.normalize(a, "html", "Typefully") == monitor.normalize(b, "html", "Typefully")


def test_missing_source_never_initializes_empty_baseline(tmp_path):
    result = monitor.collect(tmp_path, lambda _: "", SOURCES)
    assert result["status"] == "degraded"
    assert result["initialized"] == []
    assert json.loads((tmp_path / "pending-v2.json").read_text()) == {}


def api_spec(max_length=32):
    return {
        "openapi": "3.1.0",
        "info": {"title": "Typefully Public API", "version": "2.0.0"},
        "paths": {"/v2/me": {"get": {"responses": {"200": {"description": "OK"}}}}},
        "components": {
            "schemas": {
                "Tag": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "maxLength": max_length},
                        "example": {"type": "string", "maxLength": 2},
                    },
                }
            }
        },
    }


def api_page(spec, wrapper="direct"):
    encoded = json.dumps(spec)
    if wrapper == "flight":
        encoded = (
            "self.__next_f.push("
            + json.dumps([1, '7:["$","Api",null,{"spec":' + encoded + "}]\n"])
            + ")"
        )
    elif wrapper == "parse":
        encoded = "window.spec = JSON.parse(" + json.dumps(encoded) + ")"
    return page() + '<script type="application/json">' + encoded + "</script>"


@pytest.mark.parametrize("wrapper", ["direct", "flight", "parse"])
def test_schema_only_changes_are_detected(tmp_path, wrapper):
    sources = {
        "api-docs": ("https://example.invalid", "html", "Typefully"),
        "api-schema": ("https://example.invalid", "openapi", "Typefully"),
    }
    calls = []

    def fetch(_):
        calls.append(True)
        return api_page(api_spec(), wrapper)

    monitor.collect(tmp_path, fetch, sources)
    assert len(calls) == 1  # docs and schema share one consistent public response
    monitor.commit(tmp_path)
    result = monitor.collect(tmp_path, lambda _: api_page(api_spec(33), wrapper), sources)
    assert result["changed"] == ["api-schema"]
    assert result["report_needed"]


def test_flight_schema_can_span_scripts():
    encoded = '7:["$","Api",null,{"spec":' + json.dumps(api_spec()) + "}]\n"
    middle = len(encoded) // 2
    raw = page() + "".join(
        "<script>self.__next_f.push(" + json.dumps([1, part]) + ")</script>"
        for part in (encoded[:middle], encoded[middle:])
    )
    assert monitor.extract_openapi(raw) == api_spec()


def test_schema_digest_ignores_nonce_and_generated_examples():
    first = api_spec()
    first["components"]["schemas"]["Tag"]["examples"] = [{"created_at": "2026-11-05T00:00:00Z"}]
    second = api_spec()
    second["components"]["schemas"]["Tag"]["examples"] = [{"created_at": "2026-11-06T00:00:00Z"}]
    a = api_page(first) + '<script>nonce="1"</script>'
    b = api_page(second) + '<script>nonce="2"</script>'
    assert monitor.normalize(a, "openapi", "Typefully") == monitor.normalize(
        b, "openapi", "Typefully"
    )
    second["components"]["schemas"]["Tag"]["properties"]["example"]["maxLength"] = 3
    assert monitor.normalize(a, "openapi", "Typefully") != monitor.normalize(
        api_page(second), "openapi", "Typefully"
    )


@pytest.mark.parametrize(
    "raw", [page(), api_page({"openapi": "3.1.0"}), page() + '<script>{"openapi":"3.1.0",</script>']
)
def test_missing_or_invalid_schema_preserves_baseline(tmp_path, raw):
    sources = {"api-schema": ("https://example.invalid", "openapi", "Typefully")}
    monitor.collect(tmp_path, lambda _: api_page(api_spec()), sources)
    monitor.commit(tmp_path)
    old = (tmp_path / "baseline-v2.json").read_text()
    result = monitor.collect(tmp_path, lambda _: raw, sources)
    assert result["status"] == "degraded"
    assert result["failed"] == [{"source": "api-schema", "error": "ValueError"}]
    monitor.commit(tmp_path)
    assert (tmp_path / "baseline-v2.json").read_text() == old


def test_schema_reordering_is_ignored_but_operations_and_deprecations_are_not():
    first = api_spec()
    second = dict(reversed(list(first.items())))
    assert monitor.normalize(api_page(first), "openapi", "Typefully") == monitor.normalize(
        api_page(second), "openapi", "Typefully"
    )
    second["paths"]["/v2/me"]["get"]["deprecated"] = True
    assert '"deprecated":true' in monitor.normalize(api_page(second), "openapi", "Typefully")


def test_conflicting_specs_are_degraded():
    with pytest.raises(ValueError, match="conflicting"):
        monitor.extract_openapi(api_page(api_spec()) + api_page(api_spec(33)))
