-- Dedicated identity database. Never apply to the aggregate telemetry database.
CREATE TABLE IF NOT EXISTS profile_budget (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    day INTEGER NOT NULL,
    day_requests INTEGER NOT NULL CHECK (day_requests BETWEEN 0 AND 2000),
    day_admissions INTEGER NOT NULL CHECK (day_admissions BETWEEN 0 AND 50),
    minute INTEGER NOT NULL,
    minute_requests INTEGER NOT NULL CHECK (minute_requests BETWEEN 0 AND 30)
);
INSERT OR IGNORE INTO profile_budget VALUES (1, -1, 0, 0, -1, 0);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    token_hash TEXT PRIMARY KEY CHECK (length(token_hash) = 64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
    profiles_json TEXT,
    consent_revision TEXT NOT NULL CHECK (consent_revision = '3'),
    status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'revoked')),
    expires_at INTEGER NOT NULL CHECK (typeof(expires_at) = 'integer' AND expires_at > 0),
    CHECK ((status IN ('pending', 'revoked') AND profiles_json IS NULL)
        OR (status = 'active' AND profiles_json IS NOT NULL AND json_valid(profiles_json)
            AND json_type(profiles_json) = 'array'
            AND json_array_length(profiles_json) <= 600
            AND length(CAST(profiles_json AS BLOB)) <= 65536))
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS profile_expiry ON profile_snapshots(expires_at);

-- Atomic checks apply even to simultaneous registrations across Worker instances.
CREATE TRIGGER IF NOT EXISTS profile_admission_limit BEFORE INSERT ON profile_snapshots
WHEN NOT EXISTS (SELECT 1 FROM profile_snapshots WHERE token_hash = NEW.token_hash)
BEGIN
    SELECT CASE WHEN (SELECT day_admissions FROM profile_budget WHERE id = 1) >= 50
        THEN RAISE(ABORT, 'profile_admission_limit') END;
    SELECT CASE WHEN (SELECT COUNT(*) FROM profile_snapshots) >= 1000
        THEN RAISE(ABORT, 'profile_capacity') END;
END;
CREATE TRIGGER IF NOT EXISTS profile_admission_count AFTER INSERT ON profile_snapshots
BEGIN
    UPDATE profile_budget SET day_admissions = day_admissions + 1 WHERE id = 1;
END;
