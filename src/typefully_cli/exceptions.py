"""Exception hierarchy for Typefully CLI."""

from __future__ import annotations

import json
import math
import re


class TypefullyError(Exception):
    """Base exception for all Typefully CLI errors."""

    code: str = "unknown"
    hint: str = ""

    def __init__(self, message: str, *, code: str | None = None, hint: str = ""):
        super().__init__(message)
        if code is not None:
            self.code = code
        if hint:
            self.hint = hint

    def to_dict(self) -> dict:
        d: dict = {"code": self.code, "message": str(self)}
        if self.hint:
            d["hint"] = self.hint
        return d


class AuthError(TypefullyError):
    """Authentication or credential error."""

    code = "auth_failed"

    def __init__(self, message: str = "No API key found", *, hint: str = ""):
        if not hint:
            hint = (
                "Set TYPEFULLY_API_KEY, pass --api-key, "
                "or run: typefully config set api_key <key>"
            )
        super().__init__(message, hint=hint)


def _upstream_diagnostics(body):
    """Bound and redact optional parsed diagnostics; never retain an arbitrary raw body."""
    if len(body) > 262144:
        return None, True
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError, RecursionError):
        return None, False
    if not isinstance(parsed, (dict, list)):
        return None, False
    truncated = [False]
    sensitive = re.compile(
        r"api.?key|authorization|password|secret|token|cookie|^input$|^headers$|^request$",
        re.IGNORECASE,
    )

    def clean(value, depth=0):
        if depth > 8:
            truncated[0] = True
            return "[truncated]"
        if isinstance(value, dict):
            if len(value) > 50:
                truncated[0] = True
            return {
                key[:128]: "[redacted]" if sensitive.search(key) else clean(item, depth + 1)
                for key, item in list(value.items())[:50]
            }
        if isinstance(value, list):
            if len(value) > 100:
                truncated[0] = True
            return [clean(item, depth + 1) for item in value[:100]]
        if isinstance(value, str):
            value = re.sub(r'(?i)\bBearer\s+[^\s"<>]+', "Bearer [redacted]", value)
            value = re.sub(r"\btf_[A-Za-z0-9_-]+", "[redacted]", value)
            value = re.sub(
                r'(?i)((?:api[_-]?key|token|secret|password)=)[^&\s"<>]+',
                r"\1[redacted]", value,
            )
            if len(value) > 2048:
                truncated[0] = True
            return value[:2048]
        if isinstance(value, float) and not math.isfinite(value):
            truncated[0] = True
            return None
        return value

    safe = clean(parsed)
    encoded = json.dumps(safe)
    if len(encoded) > 16384:
        # A bounded preview of already-redacted diagnostics, never the raw body.
        safe = {"preview": encoded[:2048]}
        truncated[0] = True
    return safe, truncated[0]


class APIError(TypefullyError):
    """HTTP error from the Typefully API."""

    code = "api_error"

    def __init__(self, status_code: int, body: str, *, hint: str = ""):
        self.status_code = status_code
        self.upstream, self.upstream_truncated = _upstream_diagnostics(body)
        super().__init__(f"API returned {status_code}: {body[:200]}", hint=hint)

    @property
    def user_message(self) -> str:
        """Clean message without raw upstream body, safe for stdout."""
        return f"API error (HTTP {self.status_code})"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["status"] = self.status_code
        if self.upstream is not None:
            d["upstream"] = self.upstream
        if self.upstream_truncated:
            d["upstream_truncated"] = True
        return d


class AccountError(TypefullyError):
    """Account resolution error."""

    code = "no_account"

    def __init__(self, message: str = "No account specified", *, hint: str = ""):
        if not hint:
            hint = "Pass --account NAME or run: typefully config set default_account NAME"
        super().__init__(message, hint=hint)


class BatchParseError(TypefullyError):
    """Error parsing a batch file."""

    code = "batch_parse_error"


class MediaUploadError(TypefullyError):
    """Error during media upload."""

    code = "media_upload_error"
