"""Typefully API client. Thin HTTP wrapper over the v2 API."""

from __future__ import annotations

import sys
import time

import httpx

from typefully_cli.exceptions import AccountError, APIError


class TypefullyClient:
    BASE_URL = "https://api.typefully.com/v2"
    RATE_LIMIT_DELAY = 0.3

    def __init__(self, api_key: str, base_url: str | None = None, debug: bool = False):
        self._client = httpx.Client(
            base_url=base_url or self.BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        self._social_sets_cache: list[dict] | None = None
        self._debug = debug

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TypefullyClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # --- Core request ---

    def _request(self, method: str, path: str, **kwargs: object) -> dict | None:
        if self._debug:
            params = kwargs.get("params", "")
            sys.stderr.write(f"[DEBUG] {method} {path} {params}\n")
        try:
            resp = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise APIError(0, "Request timed out")
        except httpx.HTTPError as e:
            raise APIError(0, f"Network error: {e}")
        if self._debug:
            sys.stderr.write(f"[DEBUG] {resp.status_code} ({resp.elapsed.total_seconds():.2f}s)\n")
        if resp.status_code == 204:
            return None
        if not resp.is_success:
            raise APIError(resp.status_code, resp.text)
        try:
            return resp.json()
        except (ValueError, KeyError):
            raise APIError(resp.status_code, "Invalid JSON response")

    # --- Account resolution ---

    def get_social_sets(self) -> list[dict]:
        if self._social_sets_cache is not None:
            return self._social_sets_cache
        data = self._request("GET", "/social-sets", params={"limit": 50})
        self._social_sets_cache = data.get("results", []) if data else []
        return self._social_sets_cache

    def resolve_account(self, name_or_id: str | None, config_default: str = "") -> int:
        """Resolve account to social_set_id.

        Priority: name_or_id arg > config_default.
        Matches: exact numeric ID > case-insensitive username > case-insensitive name.
        """
        value = name_or_id or config_default
        if not value:
            raise AccountError()

        sets = self.get_social_sets()
        if not sets:
            raise AccountError(
                "No social sets found for this API key",
                hint="Check your Typefully account has connected social profiles",
            )

        # Try exact numeric ID
        try:
            numeric_id = int(value)
            for s in sets:
                if s.get("id") == numeric_id:
                    return numeric_id
        except ValueError:
            pass

        # Case-insensitive username match
        lower = value.lower()
        for s in sets:
            if s.get("username", "").lower() == lower:
                return s["id"]

        # Case-insensitive name match
        for s in sets:
            if s.get("name", "").lower() == lower:
                return s["id"]

        available = ", ".join(
            s.get("username") or s.get("name", str(s.get("id", "?"))) for s in sets
        )
        raise AccountError(
            f"Account '{value}' not found",
            hint=f"Available accounts: {available}",
        )

    # --- User ---

    def me(self) -> dict:
        return self._request("GET", "/me") or {}

    # --- Social sets ---

    def get_social_set(self, social_set_id: int) -> dict:
        return self._request("GET", f"/social-sets/{social_set_id}") or {}

    # --- Drafts ---

    def create_draft(self, social_set_id: int, payload: dict) -> dict:
        return self._request("POST", f"/social-sets/{social_set_id}/drafts", json=payload) or {}

    def get_draft(self, social_set_id: int, draft_id: str) -> dict:
        return self._request("GET", f"/social-sets/{social_set_id}/drafts/{draft_id}") or {}

    def update_draft(self, social_set_id: int, draft_id: str, payload: dict) -> dict:
        return (
            self._request("PATCH", f"/social-sets/{social_set_id}/drafts/{draft_id}", json=payload)
            or {}
        )

    def delete_draft(self, social_set_id: int, draft_id: str) -> None:
        self._request("DELETE", f"/social-sets/{social_set_id}/drafts/{draft_id}")

    def list_drafts(self, social_set_id: int, **params: object) -> dict:
        return (
            self._request("GET", f"/social-sets/{social_set_id}/drafts", params=params) or {}
        )

    # --- Tags ---

    def list_tags(self, social_set_id: int, limit: int = 50, offset: int = 0) -> dict:
        return (
            self._request(
                "GET",
                f"/social-sets/{social_set_id}/tags",
                params={"limit": limit, "offset": offset},
            )
            or {}
        )

    def create_tag(self, social_set_id: int, name: str) -> dict:
        return (
            self._request("POST", f"/social-sets/{social_set_id}/tags", json={"name": name}) or {}
        )

    def ensure_tags(self, social_set_id: int, tag_names: list[str]) -> list[str]:
        """Create any tags that don't exist yet. Returns list of warnings."""
        if not tag_names:
            return []
        warnings: list[str] = []
        existing_names: set[str] = set()
        offset = 0
        while True:
            page = self.list_tags(social_set_id, limit=50, offset=offset)
            results = page.get("results", [])
            existing_names.update(t.get("name", "").lower() for t in results)
            if len(results) < 50:
                break
            offset += 50
        for name in tag_names:
            if name.lower() not in existing_names:
                try:
                    self.create_tag(social_set_id, name)
                except APIError:
                    warnings.append(f"Could not create tag '{name}'")
        return warnings

    # --- Media ---

    def request_upload(self, social_set_id: int, file_name: str) -> dict:
        return (
            self._request(
                "POST",
                f"/social-sets/{social_set_id}/media/upload",
                json={"file_name": file_name},
            )
            or {}
        )

    def upload_to_s3(self, upload_url: str, file_path: str) -> None:
        """Upload file to S3 presigned URL. No Content-Type header (breaks signature)."""
        with open(file_path, "rb") as f:
            resp = httpx.put(upload_url, content=f.read(), timeout=120.0)
        if not resp.is_success:
            raise APIError(resp.status_code, "S3 upload failed")

    def get_media(self, social_set_id: int, media_id: str) -> dict:
        """Get current media status."""
        return self._request("GET", f"/social-sets/{social_set_id}/media/{media_id}") or {}

    # --- Recent (with pagination) ---

    def list_recent(
        self,
        social_set_id: int,
        limit: int = 3,
        since: str = "",
        until: str = "",
    ) -> list[dict]:
        """List recently published posts. Paginates if date range given."""
        if not since and not until:
            data = self.list_drafts(
                social_set_id,
                status="published",
                order_by="-published_at",
                limit=limit,
            )
            return data.get("results", [])

        # Paginate through date range
        results: list[dict] = []
        offset = 0
        page_size = 50
        while True:
            data = self.list_drafts(
                social_set_id,
                status="published",
                order_by="-published_at",
                limit=page_size,
                offset=offset,
            )
            page = data.get("results", [])
            if not page:
                break
            for d in page:
                raw_pub = d.get("published_at")
                if not raw_pub:
                    continue
                pub = raw_pub[:10]
                if until and pub > until:
                    continue
                if since and pub < since:
                    return results
                results.append(d)
            if len(page) < page_size:
                break
            offset += page_size
        return results

    # --- Rate-limited batch operations ---

    def rate_delay(self) -> None:
        time.sleep(self.RATE_LIMIT_DELAY)
