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
