-- Dedicated identity database. Never apply to the aggregate telemetry database.
CREATE TABLE IF NOT EXISTS profile_snapshots (
    token_hash TEXT PRIMARY KEY,
    profiles_json TEXT CHECK (profiles_json IS NULL OR json_valid(profiles_json)),
    consent_revision TEXT NOT NULL,
    expires_at INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS profile_expiry ON profile_snapshots(expires_at);
-- NULL profiles_json is a withdrawal tombstone containing no social identifiers.
