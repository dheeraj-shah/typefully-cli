"""Media upload: presigned URL + S3 PUT + poll for ready."""

from __future__ import annotations

import os
import re
import time

from typefully_cli.client import TypefullyClient
from typefully_cli.console import Console
from typefully_cli.exceptions import MediaUploadError

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "pdf"}
SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.()\-]")


def _sanitize_filename(name: str) -> str:
    """Sanitize filename to match Typefully's allowed charset.

    Replaces disallowed characters with underscore. Validates extension.
    """
    stem, _, ext = name.rpartition(".")
    if not ext or ext.lower() not in ALLOWED_EXTENSIONS:
        raise MediaUploadError(
            f"Unsupported file type: .{ext}" if ext else "No file extension",
            hint=f"Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    safe_stem = SAFE_NAME_RE.sub("_", stem) or "upload"
    # The public API caps the complete filename at 255 characters.
    safe_stem = safe_stem[:254 - len(ext)]
    return f"{safe_stem}.{ext}"


def upload_media(
    client: TypefullyClient,
    social_set_id: int,
    file_path: str,
    console: Console,
    timeout: int = 60,
    alt_text: str | None = None,
) -> dict:
    """Upload a media file and poll until ready. Returns {media_id, status}."""
    if not os.path.isfile(file_path):
        raise MediaUploadError(f"File not found: {file_path}")

    file_name = _sanitize_filename(os.path.basename(file_path))

    # Step 1: Get presigned upload URL
    console.status(f"Requesting upload URL for {file_name}...")
    upload_response = client.request_upload(social_set_id, file_name, **({"alt_text": alt_text} if alt_text is not None else {}))
    media_id = upload_response.get("media_id", "")
    upload_url = upload_response.get("upload_url", "")
    if not media_id or not upload_url:
        raise MediaUploadError("API did not return media_id or upload_url")

    # Step 2: Upload to S3
    console.status(f"Uploading {file_name}...")
    client.upload_to_s3(upload_url, file_path)

    # Step 3: Poll for processing
    console.status("Processing...")
    max_polls = max(1, (timeout + 1) // 2)
    deadline = time.monotonic() + timeout
    with console.progress("Processing media...") as progress:
        task = progress.add_task("Processing...", total=max_polls)
        data = {}
        for _ in range(max_polls):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(2, remaining))
            progress.advance(task)
            data = client.get_media(social_set_id, media_id)
            status = data.get("status", "unknown")
            if status in ("ready", "completed"):
                return {"media_id": media_id, "status": "ready"}
            if status == "failed":
                raise MediaUploadError(
                    f"Media {media_id} processing failed: {data.get('error_reason') or 'unknown reason'}",
                    hint="Check the file format and request a new upload URL before retrying",
                )

    raise MediaUploadError(
        f"Media {media_id} is still {data.get('status', 'unknown')} after {timeout}s",
        code="media_processing_timeout",
        hint=f"Processing may continue; poll with: typefully media-status {media_id}",
    )
