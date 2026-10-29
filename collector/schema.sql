CREATE TABLE IF NOT EXISTS daily_counts (
    day TEXT NOT NULL,
    version TEXT NOT NULL,
    category TEXT NOT NULL,
    count INTEGER NOT NULL CHECK (count > 0),
    PRIMARY KEY (day, version, category)
) WITHOUT ROWID;
