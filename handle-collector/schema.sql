-- Dedicated identity database. Never apply to the aggregate telemetry database.
CREATE TABLE IF NOT EXISTS shared_handles (
    token_hash TEXT PRIMARY KEY,
    handle TEXT NOT NULL,
    consent_revision TEXT NOT NULL,
    expires_at INTEGER NOT NULL
) WITHOUT ROWID;
