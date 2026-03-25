"""Exception hierarchy for Typefully CLI."""

from __future__ import annotations


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


class APIError(TypefullyError):
    """HTTP error from the Typefully API."""

    code = "api_error"

    def __init__(self, status_code: int, body: str, *, hint: str = ""):
        self.status_code = status_code
        super().__init__(f"API returned {status_code}: {body[:200]}", hint=hint)

    @property
    def user_message(self) -> str:
        """Clean message without raw upstream body, safe for stdout."""
        return f"API error (HTTP {self.status_code})"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["status"] = self.status_code
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
