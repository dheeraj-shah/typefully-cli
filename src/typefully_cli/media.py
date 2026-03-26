"""Media upload: presigned URL + S3 PUT + poll for ready."""

from __future__ import annotations

import os
import re

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
    return f"{safe_stem}.{ext}"


def upload_media(
    client: TypefullyClient,
    social_set_id: int,
    file_path: str,
    console: Console,
) -> dict:
    """Upload a media file and poll until ready. Returns {media_id, status}."""
    if not os.path.isfile(file_path):
        raise MediaUploadError(f"File not found: {file_path}")

    file_name = _sanitize_filename(os.path.basename(file_path))

    # Step 1: Get presigned upload URL
    console.status(f"Requesting upload URL for {file_name}...")
    upload_response = client.request_upload(social_set_id, file_name)
    media_id = upload_response.get("media_id", "")
    upload_url = upload_response.get("upload_url", "")
    if not media_id or not upload_url:
        raise MediaUploadError("API did not return media_id or upload_url")

    # Step 2: Upload to S3
    console.status(f"Uploading {file_name}...")
    client.upload_to_s3(upload_url, file_path)

    # Step 3: Poll for processing
    console.status("Processing...")
    with console.progress("Processing media...") as progress:
        task = progress.add_task("Processing...", total=30)
        data = {}
        for _ in range(30):
            import time

            time.sleep(2)
            progress.advance(task)
            data = client.get_media(social_set_id, media_id)
            status = data.get("status", "unknown")
            if status in ("ready", "completed"):
                return {"media_id": media_id, "status": "ready"}

    return {"media_id": media_id, "status": data.get("status", "unknown")}
