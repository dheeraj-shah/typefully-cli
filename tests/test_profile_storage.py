"""Actual collector SQL on local SQLite, including ceilings and racing admissions; never D1."""

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "profile-collector"
SQL = dict(re.findall(r"(\w+):\s*`(.*?)`", (ROOT / "storage.mjs").read_text(), re.S))
NOW = 1800000000
RETENTION = 90 * 86400
PROFILE = json.dumps([{"platform": "substack", "username": "synthetic"}])


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()


def database(path=":memory:"):
    db = sqlite3.connect(path)
    db.executescript((ROOT / "schema.sql").read_text())
    return db


def spend(db, now=NOW):
    day, minute = now // 86400, now // 60
    return db.execute(SQL["budget"], (day, day, day, minute, minute, day, day, minute, minute)).rowcount


def register(db, token, now=NOW):
    return db.execute(SQL["register"], (key(token), now + 3600)).rowcount


def sync(db, token, now=NOW, profile=PROFILE):
    return db.execute(SQL["sync"], (profile, now + RETENTION, key(token), now, now + RETENTION - 86400)).rowcount


def withdraw(db, token, now=NOW):
    return db.execute(SQL["withdraw"], (now, now + RETENTION, key(token))).rowcount


def row(db, token):
    return db.execute("SELECT profiles_json, status, expires_at FROM profile_snapshots WHERE token_hash=?",
                      (key(token),)).fetchone()


def test_unknown_sync_and_withdraw_never_allocate_storage_and_known_deletion_stays_idempotent():
    db = database()
    assert sync(db, "unknown") == 0
    for i in range(500):
        assert withdraw(db, f"unknown-{i}") == 0
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (0,)
    assert spend(db) == 1
    assert register(db, "a") == 1
    assert sync(db, "a") == 1
    assert withdraw(db, "a") == 1
    tombstone = row(db, "a")
    assert tombstone[:2] == (None, "revoked")
    assert withdraw(db, "a", NOW + 86400) == 0
    assert row(db, "a") == tombstone
    assert sync(db, "a", NOW + 86400) == 0
    assert register(db, "a", NOW + 86400) == 0
    assert row(db, "a") == tombstone


def test_actual_sql_enforces_daily_sync_and_rolling_snapshot_replacement_without_history():
    db = database()
    spend(db)
    register(db, "a")
    assert sync(db, "a") == 1
    first = row(db, "a")
    assert sync(db, "a", NOW + 86399) == 0
    assert row(db, "a") == first
    replacement = json.dumps([{"platform": "substack", "username": "synthetic_new"}])
    assert sync(db, "a", NOW + 86400, replacement) == 1
    assert row(db, "a") == (replacement, "active", first[2] + 86400)
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (1,)


def test_global_request_budget_has_strict_minute_day_and_monotonic_window_limits():
    db = database()
    for _ in range(30):
        assert spend(db) == 1
    for _ in range(10):
        assert spend(db) == 0
    assert spend(db, NOW + 60) == 1
    assert spend(db, NOW) == 0  # An older Worker clock must not reset the shared counter backwards.
    for number in range(31, 2000):
        assert spend(db, NOW + (number // 30) * 60) == 1
    assert spend(db, NOW + 7200) == 0
    assert db.execute("SELECT day_requests FROM profile_budget").fetchone() == (2000,)
    assert spend(db, NOW + 86400) == 1
    assert db.execute("SELECT day_requests, minute_requests, day_admissions FROM profile_budget").fetchone() == (1, 1, 0)
    assert db.execute("SELECT COUNT(*) FROM profile_budget").fetchone() == (1,)


def test_fresh_admissions_are_capped_per_day_and_expiry_does_not_refund_the_quota():
    db = database()
    spend(db)
    for i in range(50):
        assert register(db, str(i)) == 1
    assert register(db, "0") == 0  # Replay is idempotent, not another admission or lease extension.
    with pytest.raises(sqlite3.IntegrityError, match="profile_admission_limit"):
        register(db, "over-limit")
    db.execute(SQL["cleanup"], (NOW + 3601,))
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (0,)
    with pytest.raises(sqlite3.IntegrityError, match="profile_admission_limit"):
        register(db, "after-expiry", NOW + 3601)
    spend(db, NOW + 86400)
    assert register(db, "new-day", NOW + 86400) == 1


def test_capacity_includes_active_pending_and_revoked_and_does_not_block_legitimate_deletion():
    db = database()
    for day in range(20):
        now = NOW + day * 86400
        assert spend(db, now) == 1
        for number in range(50):
            token = f"{day}-{number}"
            register(db, token, now)
            sync(db, token, now)
    now = NOW + 20 * 86400
    assert spend(db, now) == 1
    with pytest.raises(sqlite3.IntegrityError, match="profile_capacity"):
        register(db, "capacity-overflow", now)
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (1000,)
    db.execute("UPDATE profile_budget SET day_requests=2000, day_admissions=50, minute_requests=30")
    assert withdraw(db, "0-0", now) == 1
    assert row(db, "0-0")[:2] == (None, "revoked")
    assert withdraw(db, "unknown", now) == 0
    assert withdraw(db, "0-0", now + 86400) == 0
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (1000,)


def test_two_connections_cannot_exceed_daily_admissions_after_a_stale_precheck(tmp_path):
    path = tmp_path / "collector.sqlite"
    db1 = database(path)
    spend(db1)
    for i in range(49):
        register(db1, str(i))
    db1.commit()
    db2 = sqlite3.connect(path)
    for db in (db1, db2):
        assert db.execute("SELECT day_admissions FROM profile_budget").fetchone() == (49,)
    register(db1, "connection-one")
    db1.commit()
    with pytest.raises(sqlite3.IntegrityError, match="profile_admission_limit"):
        register(db2, "connection-two")
    assert db1.execute("SELECT day_admissions FROM profile_budget").fetchone() == (50,)


def test_schema_enforces_payload_size_and_withdrawal_does_not_revive_expired_reservations():
    db = database()
    spend(db)
    register(db, "a")
    oversized = json.dumps([{"platform": "substack", "username": "x" * 65536}])
    with pytest.raises(sqlite3.IntegrityError):
        sync(db, "a", profile=oversized)
    assert row(db, "a")[1] == "pending"
    assert withdraw(db, "a", NOW + 3601) == 1
    assert row(db, "a")[2] == NOW + 3600
    db.execute(SQL["cleanup"], (NOW + 3601,))
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (0,)
