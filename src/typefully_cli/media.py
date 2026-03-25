"""Media upload: presigned URL + S3 PUT + poll for ready."""

from __future__ import annotations

import os

from typefully_cli.client import TypefullyClient
from typefully_cli.console import Console
from typefully_cli.exceptions import MediaUploadError


def upload_media(
    client: TypefullyClient,
    social_set_id: int,
    file_path: str,
    console: Console,
) -> dict:
    """Upload a media file and poll until ready. Returns {media_id, status}."""
    if not os.path.isfile(file_path):
        raise MediaUploadError(f"File not found: {file_path}")

    file_name = os.path.basename(file_path)

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
        for attempt in range(30):
            import time

            time.sleep(2)
            progress.advance(task)
            data = client._request("GET", f"/social-sets/{social_set_id}/media/{media_id}") or {}
            status = data.get("status", "unknown")
            if status in ("ready", "completed"):
                return {"media_id": media_id, "status": "ready"}

    return {"media_id": media_id, "status": data.get("status", "unknown")}
