"""Tests for batch file parser."""

import pytest
from typefully_cli.batch import BatchEntry, merge_defaults, parse_batch_file
from typefully_cli.exceptions import BatchParseError


class TestParseBatchFile:
    def test_single_draft(self):
        content = "Hello world"
        entries = parse_batch_file(content)
        assert len(entries) == 1
        assert entries[0].posts == ["Hello world"]
        assert entries[0].schedule is None
        assert entries[0].tags == []

    def test_multiple_drafts(self):
        content = "First draft\n---\nSecond draft\n---\nThird draft"
        entries = parse_batch_file(content)
        assert len(entries) == 3
        assert entries[0].posts == ["First draft"]
        assert entries[1].posts == ["Second draft"]
        assert entries[2].posts == ["Third draft"]

    def test_thread(self):
        content = "Post 1\n===\nPost 2\n===\nPost 3"
        entries = parse_batch_file(content)
        assert len(entries) == 1
        assert entries[0].posts == ["Post 1", "Post 2", "Post 3"]

    def test_mixed_threads_and_singles(self):
        content = "Thread post 1\n===\nThread post 2\n---\nSingle post"
        entries = parse_batch_file(content)
        assert len(entries) == 2
        assert len(entries[0].posts) == 2
        assert len(entries[1].posts) == 1

    def test_metadata_parsing(self):
        content = "schedule: 2026-03-25T10:00:00Z\ntag: launch\ntitle: My Title\nscratchpad: Notes\nmedia: abc,def\nThe actual post"
        entries = parse_batch_file(content)
        assert len(entries) == 1
        e = entries[0]
        assert e.schedule == "2026-03-25T10:00:00Z"
        assert e.tags == ["launch"]
        assert e.title == "My Title"
        assert e.scratchpad == "Notes"
        assert e.media_ids == ["abc", "def"]
        assert e.posts == ["The actual post"]

    def test_metadata_case_insensitive(self):
        content = "Schedule: next\nTag: foo\nPost text"
        entries = parse_batch_file(content)
        assert entries[0].schedule == "next"
        assert entries[0].tags == ["foo"]

    def test_multiple_tags(self):
        content = "tag: alpha\ntag: beta\nPost"
        entries = parse_batch_file(content)
        assert entries[0].tags == ["alpha", "beta"]

    def test_empty_blocks_skipped(self):
        content = "Post 1\n---\n\n---\nPost 2"
        entries = parse_batch_file(content)
        assert len(entries) == 2

    def test_empty_file_raises(self):
        with pytest.raises(BatchParseError):
            parse_batch_file("")

    def test_metadata_only_block_skipped(self):
        content = "schedule: next\ntag: foo\n---\nActual post"
        entries = parse_batch_file(content)
        assert len(entries) == 1
        assert entries[0].posts == ["Actual post"]

    def test_to_dict(self):
        entry = BatchEntry(posts=["a", "b"], schedule="next", tags=["t1"])
        d = entry.to_dict()
        assert d["type"] == "thread"
        assert d["post_count"] == 2
        assert d["schedule"] == "next"

    def test_to_dict_single(self):
        entry = BatchEntry(posts=["solo"])
        d = entry.to_dict()
        assert d["type"] == "single"
        assert d["post_count"] == 1


class TestMergeDefaults:
    def test_schedule_default_applied(self):
        entries = [BatchEntry(posts=["a"]), BatchEntry(posts=["b"], schedule="now")]
        merge_defaults(entries, default_schedule="next")
        assert entries[0].schedule == "next"
        assert entries[1].schedule == "now"  # not overwritten

    def test_tags_default_merged(self):
        entries = [BatchEntry(posts=["a"], tags=["existing"])]
        merge_defaults(entries, default_tags=("new", "existing"))
        assert "new" in entries[0].tags
        assert entries[0].tags.count("existing") == 1  # no duplicate
