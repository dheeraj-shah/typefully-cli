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
