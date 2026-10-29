"""Explicit JSON request input and media metadata commands (no arbitrary HTTP route)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import click

from typefully_cli.console import write_success
from typefully_cli.exceptions import TypefullyError


SCHEMA_FILE = Path(__file__).with_name("request-schemas.json")


def _invalid(message):
    raise TypefullyError(message, code="invalid_input")


def _validate(value, schema, schemas, path="payload"):
    """Validate the finite JSON Schema vocabulary in our reviewed request snapshot.

    This is not a general JSON Schema implementation. The snapshot vocabulary has
    a regression test; adding upstream keywords requires implementing them here.
    Server-side account, platform, scheduling and content rules remain authoritative.
    """
    if "$ref" in schema:
        _validate(value, schemas[schema["$ref"].rsplit("/", 1)[-1]], schemas, path)
    for sub in schema.get("allOf", []):
        _validate(value, sub, schemas, path)
    if "if" in schema:
        try:
            _validate(value, schema["if"], schemas, path)
        except TypefullyError:
            pass
        else:
            _validate(value, schema.get("then", {}), schemas, path)
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            try:
                _validate(value, sub, schemas, path)
                break
            except TypefullyError:
                continue
        else:
            _invalid(f"{path}: value does not match an allowed schema")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "null": type(None),
        "integer": int,
        "number": (int, float),
    }
    kind = schema.get("type")
    if kind and (
        not isinstance(value, types[kind])
        or (kind in ("integer", "number") and isinstance(value, bool))
    ):
        _invalid(f"{path}: expected {kind}")
    if "enum" in schema and value not in schema["enum"]:
        _invalid(f"{path}: value is not an allowed option")
    if "const" in schema and value != schema["const"]:
        _invalid(f"{path}: value must match the documented constant")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                _invalid(f"{path}: missing {key}")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(props)
            if unknown:
                _invalid(f"{path}: unsupported field {sorted(unknown)[0]}")
        for key, item in value.items():
            if key in props:
                _validate(item, props[key], schemas, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", len(value)):
            _invalid(f"{path}: too many items")
        for i, item in enumerate(value):
            _validate(item, schema.get("items", {}), schemas, f"{path}[{i}]")
    if isinstance(value, str):
        if len(value) > schema.get("maxLength", len(value)):
            _invalid(f"{path}: value is too long")
        if schema.get("format") == "date-time":
            try:
                parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None or "T" not in value:
                    raise ValueError
            except ValueError:
                _invalid(f"{path}: expected ISO 8601 timestamp with timezone")


def validate_payload(payload, action):
    snapshot = json.loads(SCHEMA_FILE.read_text())
    schemas = snapshot["schemas"]
    root = "DraftCreateRequest" if action == "create" else "DraftUpdateRequest"
    _validate(payload, schemas[root], schemas)
    if payload.get("publish_at") is not None and payload.get("plan_at") is not None:
        _invalid("publish_at and plan_at are mutually exclusive")
    platforms = payload.get("platforms", {})
    if "x_article" in platforms:
        if len(platforms) != 1:
            _invalid("X Article must be a standalone platform payload")
        article = platforms["x_article"]
        if action == "create" and not article.get("content_markdown"):
            _invalid("X Article creation requires content_markdown")
    if not payload:
        _invalid("Empty update payload has no effect")
    return payload


def register_commands(cli):
    # Lazy import: CLI registers commands after defining its shared helpers.
    import importlib

    helpers = importlib.import_module("typefully_cli.cli")
    error_handler, shared_options = helpers.error_handler, helpers.shared_options

    @cli.command("draft-payload")
    @click.argument("action", type=click.Choice(["create", "update"]))
    @click.option(
        "--file",
        "payload_file",
        required=True,
        type=click.File("r"),
        help="JSON request file; use - for stdin. Preserves explicit null/false.",
    )
    @click.option("--draft-id", type=click.IntRange(min=1), help="Required for update only")
    @click.option(
        "--validate-only", is_flag=True, help="Validate locally without authentication or requests"
    )
    @shared_options
    @error_handler
    def draft_payload(
        action,
        payload_file,
        draft_id,
        validate_only,
        api_key,
        account,
        use_text,
        use_json,
        quiet,
        debug,
    ):
        """Create/update from the documented API request schema; always emit JSON.

        Update platform arrays replace content; include all posts/settings to keep.
        Preserve comment markers or explicitly use force_overwrite_comments.
        publish_at=now publishes; plan_at never auto-publishes. --json is OUTPUT only.
        """
        if (action == "update") != (draft_id is not None):
            _invalid("--draft-id is required for update and not allowed for create")
        try:
            payload = json.load(payload_file)
        except (ValueError, UnicodeError):
            _invalid("Request file must contain valid JSON")
        validate_payload(payload, action)
        if validate_only:
            write_success({"valid": True, "schema_date": "2026-10-29"})
            return
        client, console, cfg = helpers._get_client_and_console(api_key, quiet, debug=debug)
        with client:
            ssid = helpers._resolve_account_id(client, account, cfg)
            if action == "create":
                result = client.create_draft(ssid, payload)
            else:
                result = client.update_draft(ssid, draft_id, payload)
        write_success(result)

    @cli.command("media-update")
    @click.argument("media_id")
    @click.option("--alt-text", default=None, help="Replacement alt text, up to 1000 characters")
    @click.option("--clear-alt-text", is_flag=True, help="Explicitly clear alt text")
    @shared_options
    @error_handler
    def media_update(
        media_id, alt_text, clear_alt_text, api_key, account, use_text, use_json, quiet, debug
    ):
        """Update media alt text; always emit JSON. Attached drafts retain their snapshot."""
        if (alt_text is not None) == clear_alt_text:
            _invalid("Choose exactly one of --alt-text or --clear-alt-text")
        if alt_text is not None and len(alt_text) > 1000:
            _invalid("Alt text must be at most 1000 characters")
        if not media_id or any(c in media_id for c in "/?#"):
            _invalid("Invalid media ID")
        client, console, cfg = helpers._get_client_and_console(api_key, quiet, debug=debug)
        with client:
            ssid = helpers._resolve_account_id(client, account, cfg)
            result = client.update_media(ssid, media_id, None if clear_alt_text else alt_text)
        write_success(result)
