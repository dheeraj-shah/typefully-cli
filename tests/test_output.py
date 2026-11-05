"""Tests for Rich markup escaping in --text output."""

from unittest.mock import patch

from typefully_cli import output as fmt


def _capture_print(fn, *args):
    """Capture Rich console output as plain text."""
    with patch.object(fmt, "_console") as mock_console:
        # Collect all print calls
        printed = []
        mock_console.print = lambda *a, **kw: printed.append(" ".join(str(x) for x in a))
        fn(*args)
    return "\n".join(printed)


class TestRichMarkupEscaping:
    """Bracketed text in user content must survive Rich rendering."""

    def test_draft_post_text_preserved(self):
        data = {
            "id": 123,
            "status": "draft",
            "platforms": {
                "x": {
                    "enabled": True,
                    "posts": [{"text": "[codex-review] updated single draft"}],
                },
            },
        }
        output = _capture_print(fmt.print_draft, data)
        assert "[codex-review]" in output
        assert "updated single draft" in output

    def test_drafts_list_preview_preserved(self):
        data = {
            "count": 1,
            "results": [
                {
                    "id": 456,
                    "status": "draft",
                    "platforms": {
                        "x": {
                            "enabled": True,
                            "posts": [{"text": "[tag-name] hello world"}],
                        },
                    },
                },
            ],
        }
        output = _capture_print(fmt.print_drafts_list, data)
        assert "[tag-name]" in output

    def test_recent_post_text_preserved(self):
        posts = [
            {
                "id": 789,
                "published_at": "2026-03-26T12:00:00Z",
                "platforms": {
                    "x": {
                        "posts": [{"text": "[launch] our new feature"}],
                    },
                },
            },
        ]
        output = _capture_print(fmt.print_recent, posts)
        assert "[launch]" in output

    def test_batch_dry_run_preview_preserved(self):
        entries = [
            {"posts": ["[v2] release notes here"], "schedule": "next", "tags": []},
        ]
        output = _capture_print(fmt.print_batch_dry_run, entries)
        assert "[v2]" in output

    def test_user_name_preserved(self):
        data = {"name": "[admin] John", "email": "j@test.com", "api_key_label": "key"}
        output = _capture_print(fmt.print_user, data)
        assert "[admin] John" in output

    def test_account_detail_name_preserved(self):
        data = {
            "name": "[brand] Acme",
            "id": 1,
            "team": {"name": "[team-alpha]", "id": 2},
            "platforms": {},
        }
        output = _capture_print(fmt.print_account_detail, data)
        assert "[brand] Acme" in output
        assert "[team-alpha]" in output

    def test_draft_tags_preserved(self):
        data = {
            "id": 1,
            "status": "draft",
            "tags": [{"name": "[launch]", "slug": "launch"}],
            "platforms": {},
        }
        output = _capture_print(fmt.print_draft, data)
        assert "[launch]" in output

    def test_draft_scratchpad_preserved(self):
        data = {
            "id": 1,
            "status": "draft",
            "scratchpad_text": "[review] internal notes",
            "platforms": {},
        }
        output = _capture_print(fmt.print_draft, data)
        assert "[review] internal notes" in output

    def test_draft_title_preserved(self):
        data = {
            "id": 1,
            "status": "draft",
            "draft_title": "[wip] campaign post",
            "platforms": {},
        }
        output = _capture_print(fmt.print_draft, data)
        assert "[wip] campaign post" in output

    def test_tags_list_preserved(self):
        results = [{"name": "[beta]", "slug": "[beta-slug]"}]
        output = _capture_print(fmt.print_tags, results)
        assert "[beta]" in output
        assert "[beta-slug]" in output

    def test_batch_dry_run_schedule_and_tags_preserved(self):
        entries = [
            {"posts": ["hello"], "schedule": "[custom]", "tags": ["[launch]", "[v2]"]},
        ]
        output = _capture_print(fmt.print_batch_dry_run, entries)
        assert "[custom]" in output
        assert "[launch]" in output

    def test_accounts_table_name_preserved(self):
        """Table cells go through add_row which stores escaped strings."""
        from rich.table import Table

        results = [{"username": "[bot]", "id": 1, "name": "[brand]", "platforms": {}}]
        captured_tables = []
        with patch.object(fmt, "_console") as mock_console:
            mock_console.print = lambda *a, **kw: captured_tables.append(a[0]) if a and isinstance(a[0], Table) else None
            fmt.print_accounts(results)
        assert len(captured_tables) == 1
        table = captured_tables[0]
        # Rich Table stores cell values as Text objects; check the row data
        row_cells = [str(c) for c in table.columns[0]._cells]
        assert any("\\[bot]" in c or "[bot]" in c for c in row_cells)


def test_queue_current_response_includes_free_planned_and_scheduled_items():
    from io import StringIO
    from rich.console import Console

    stream = StringIO()
    data = {"days": [{"date": "2026-11-05", "items": [
        {"at": "2026-11-05T09:00:00Z", "kind": "queue_slot", "draft": None},
        {"at": "2026-11-05T10:00:00Z", "kind": "custom_time",
         "draft": {"id": 4, "status": "planned", "preview": "[red]planned[/red]"}},
        {"at": "2026-11-05T11:00:00Z", "kind": "queue_slot",
         "draft": {"id": 5, "status": "scheduled", "preview": "Confirmed post"}},
    ]}]}
    with patch.object(fmt, "_console", Console(file=stream, width=160, color_system=None)):
        fmt.print_queue(data)
    output = stream.getvalue()
    assert "empty queue" not in output
    assert "09:00" in output and "empty slot" in output
    assert "planned (inert; awaiting confirmation)" in output
    assert "[red]planned[/red]" in output
    assert "scheduled: Confirmed post" in output


def test_queue_legacy_response_still_renders():
    output = _capture_print(fmt.print_queue, {"slots": [{"time": "2026-11-05T09:00:00Z",
                            "draft": {"id": 1, "preview": "Legacy"}}]})
    assert "09:00" in output and "Legacy" in output


def test_queue_schedule_exposes_account_timezone():
    output = _capture_print(fmt.print_queue_schedule, {
        "timezone": "Asia/Kolkata", "rules": [{"h": 9, "m": 30, "days": ["mon"]}],
    })
    assert "Timezone: Asia/Kolkata" in output
    assert "09:30" in output


def test_article_content_and_all_platform_urls_are_visible():
    output = _capture_print(fmt.print_draft, {
        "platforms": {"x_article": {"content_markdown": "# [Title]\n\nBody [red]literal[/red]"}},
        "substack_published_url": "https://substack.com/@someone/note/c-1",
        "x_article_published_url": "https://x.com/i/article/123",
        "publish_state": "finished",
    })
    assert "X_ARTICLE" in output and "# [Title]" in output and "Body \\[red]" in output
    assert "https://substack.com/@someone/note/c-1" in output
    assert "https://x.com/i/article/123" in output
    assert "Publish state: finished" in output


def test_in_progress_publish_response_is_not_presented_as_complete():
    output = _capture_print(fmt.print_draft_short,
                            {"id": 1, "status": "draft", "publish_state": "in_progress"})
    assert "in_progress" in output
    assert "asynchronous" in output
    assert "use get" in output


def test_quota_and_current_media_metadata_are_visible_and_escaped():
    output = _capture_print(fmt.print_account_detail, {
        "publishing_quota": {"used": 3, "remaining": "unlimited", "resets_at": "2026-12-01T00:00:00Z"},
    })
    assert "used: 3" in output and "remaining: unlimited" in output
    assert "resets_at: 2026-12-01" in output
    output = _capture_print(fmt.print_media_status, {
        "media_id": "id", "status": "failed", "error_reason": "[red]bad file[/red]",
        "alt_text": "[label]", "media_urls": {"original": "https://example.invalid/media"},
    })
    assert "\\[red]bad file" in output and "\\[label]" in output
    assert "https://example.invalid/media" in output


def test_recent_article_and_non_x_published_urls():
    output = _capture_print(fmt.print_recent, [{
        "id": 1, "published_at": "2026-11-05T01:00:00Z",
        "platforms": {"x_article": {"content_markdown": "# Article\n\nBody"}},
        "linkedin_published_url": "https://www.linkedin.com/feed/update/urn:li:share:1",
        "substack_published_url": "https://substack.com/@someone/note/c-1",
        "x_article_published_url": "https://x.com/i/article/123",
    }])
    assert "# Article" in output
    assert "https://www.linkedin.com/feed/update/urn:li:share:1" in output
    assert "https://substack.com/@someone/note/c-1" in output
    assert "https://x.com/i/article/123" in output
