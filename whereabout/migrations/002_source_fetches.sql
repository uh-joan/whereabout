CREATE TABLE IF NOT EXISTS source_fetches (
    source_id TEXT NOT NULL,
    date_key  TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    PRIMARY KEY (source_id, date_key)
);
