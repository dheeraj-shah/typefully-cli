"""Local checks for constraints verified in the public Typefully API reference."""

from __future__ import annotations

import datetime
from uuid import UUID

from typefully_cli.exceptions import TypefullyError


COMMENT_PLATFORMS = ("x", "linkedin", "mastodon", "threads", "bluesky", "substack", "x_article")
DRAFT_STATUSES = ("draft", "published", "scheduled", "planned", "error", "publishing")
DRAFT_ORDERS = tuple(
    prefix + name
    for name in ("created_at", "updated_at", "scheduled_date", "published_at")
    for prefix in ("", "-")
)


def invalid(message):
    raise TypefullyError(message, code="invalid_input")


def validate_choice(value, choices, name):
    if value is not None and value not in choices:
        invalid(f"{name} must be one of: {', '.join(choices)}")


def validate_length(value, minimum, maximum, name):
    if not isinstance(value, str) or not minimum <= len(value) <= maximum:
        invalid(f"{name} must contain {minimum}..{maximum} characters")


def validate_uuid(value, name):
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError):
        invalid(f"{name} must be a UUID")


def validate_queue_dates(start, end):
    if not start or not end:
        invalid("Queue requires both --start-date and --end-date (YYYY-MM-DD)")
    delta = (datetime.date.fromisoformat(end) - datetime.date.fromisoformat(start)).days
    if delta < 0 or delta > 62:
        invalid("Queue end date must be on or after start date, at most 62 days apart")


def validate_queue_rules(rules):
    if not isinstance(rules, list):
        invalid("--rules must be a JSON array")
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict):
            invalid("Each queue rule must be an object with h, m and days")
        if set(rule) - {"h", "m", "days"}:
            invalid("Queue rules accept only h, m and days")
        for name, maximum in (("h", 23), ("m", 59)):
            value = rule.get(name)
            if type(value) is not int or not 0 <= value <= maximum:
                invalid(f"Queue rule {name} must be an integer in 0..{maximum}")
        days = rule.get("days")
        if not isinstance(days, list) or not days:
            invalid("Queue rule days must be a non-empty array")
        for day in days:
            validate_choice(day, ("mon", "tue", "wed", "thu", "fri", "sat", "sun"), "Queue day")
            if day is None:
                invalid("Queue day cannot be null")
            slot = (day, rule["h"], rule["m"])
            if slot in seen:
                invalid("Duplicate queue day and time")
            seen.add(slot)
