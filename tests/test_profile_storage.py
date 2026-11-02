"""Exercise the actual proposed Worker SQL against local SQLite; never remote D1."""

import json
import re
import sqlite3
from pathlib import Path


def test_actual_sql_replaces_snapshot_extends_expiry_and_preserves_withdrawal_tombstones():
    root = Path(__file__).resolve().parents[1] / "profile-collector"
    source = (root / "worker.mjs").read_text()
    statements = re.findall(r"prepare\(`(.*?)`\)", source, re.S)
    withdraw, sync = statements
    db = sqlite3.connect(":memory:")
    db.executescript((root / "schema.sql").read_text())
    first = json.dumps([{"platform": "substack", "username": "synthetic_first"}])
    second = json.dumps([{"platform": "substack", "username": "synthetic_new"}])
    db.execute(sync, ("hash-a", first, 100))
    db.execute(sync, ("hash-b", first, 100))
    db.execute(sync, ("hash-a", second, 200))
    assert db.execute("SELECT profiles_json, expires_at FROM profile_snapshots WHERE token_hash='hash-a'").fetchone() == (second, 200)
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (2,)
    db.execute(withdraw, ("hash-a", 300))
    assert db.execute(sync, ("hash-a", first, 400)).rowcount == 0
    assert db.execute("SELECT profiles_json FROM profile_snapshots WHERE token_hash='hash-a'").fetchone() == (None,)
    assert db.execute("SELECT profiles_json FROM profile_snapshots WHERE token_hash='hash-b'").fetchone() == (first,)
    db.execute(withdraw, ("hash-before-first-sync", 300))
    assert db.execute(sync, ("hash-before-first-sync", first, 400)).rowcount == 0
    db.execute("DELETE FROM profile_snapshots WHERE expires_at <= ?", (300,))
    assert db.execute("SELECT COUNT(*) FROM profile_snapshots").fetchone() == (0,)
