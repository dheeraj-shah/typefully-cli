"""Tests for media upload filename sanitization."""

import pytest
from typefully_cli.media import _sanitize_filename
from typefully_cli.exceptions import MediaUploadError


class TestSanitizeFilename:
    def test_spaces_replaced(self):
        assert _sanitize_filename("Comp 1.mp4") == "Comp_1.mp4"

    def test_special_chars_replaced(self):
        assert _sanitize_filename("file@name#test.jpg") == "file_name_test.jpg"

    def test_clean_name_unchanged(self):
        assert _sanitize_filename("clean_file.png") == "clean_file.png"

    def test_parens_and_hyphens_allowed(self):
        assert _sanitize_filename("file-(1).mp4") == "file-(1).mp4"

    def test_unsupported_extension_raises(self):
        with pytest.raises(MediaUploadError) as exc_info:
            _sanitize_filename("file.txt")
        assert "Unsupported" in str(exc_info.value)
        assert "Supported" in exc_info.value.hint

    def test_no_extension_raises(self):
        with pytest.raises(MediaUploadError):
            _sanitize_filename("noextension")

    def test_space_stem_becomes_underscore(self):
        assert _sanitize_filename(" .jpg") == "_.jpg"

    def test_multiple_spaces(self):
        assert _sanitize_filename("my cool photo 2.png") == "my_cool_photo_2.png"
