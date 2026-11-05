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

    def test_filename_limit_keeps_extension(self):
        name = _sanitize_filename("x" * 300 + ".JPEG")
        assert len(name) == 255
        assert name.endswith(".JPEG")


def test_failed_processing_stops_polling_and_reports_reason(tmp_path):
    from unittest.mock import MagicMock, patch
    from typefully_cli.media import upload_media

    file = tmp_path / "photo.jpg"
    file.write_bytes(b"offline dummy bytes")
    client = MagicMock()
    client.request_upload.return_value = {"media_id": "id", "upload_url": "https://example.invalid"}
    client.get_media.return_value = {"status": "failed", "error_reason": "Unsupported file format"}
    with patch("time.sleep") as sleep:
        with pytest.raises(MediaUploadError, match="Unsupported file format"):
            upload_media(client, 1, str(file), MagicMock())
    assert client.get_media.call_count == 1
    assert sleep.call_count == 1


def test_processing_timeout_is_distinct_and_keeps_polling_id(tmp_path):
    from unittest.mock import MagicMock, patch
    from typefully_cli.media import upload_media

    file = tmp_path / "photo.jpg"
    file.write_bytes(b"offline dummy bytes")
    client = MagicMock()
    client.request_upload.return_value = {"media_id": "offline-id", "upload_url": "https://example.invalid"}
    client.get_media.return_value = {"status": "processing"}
    with patch("time.sleep"), patch("time.monotonic", return_value=0):
        with pytest.raises(MediaUploadError) as caught:
            upload_media(client, 1, str(file), MagicMock(), timeout=3)
    assert caught.value.code == "media_processing_timeout"
    assert "still processing" in str(caught.value)
    assert "typefully media-status offline-id" in caught.value.hint
    assert client.get_media.call_count == 2
    assert "example.invalid" not in str(caught.value)


def test_ready_media_retains_existing_success_shape(tmp_path):
    from unittest.mock import MagicMock, patch
    from typefully_cli.media import upload_media

    file = tmp_path / "photo.jpg"
    file.write_bytes(b"offline dummy bytes")
    client = MagicMock()
    client.request_upload.return_value = {"media_id": "id", "upload_url": "https://example.invalid"}
    client.get_media.return_value = {"status": "ready"}
    with patch("time.sleep"):
        result = upload_media(client, 1, str(file), MagicMock(), timeout=1)
    assert result == {"media_id": "id", "status": "ready"}
