PRAGMA journal_mode=WAL;
PRAGMA user_version=1;

CREATE TABLE IF NOT EXISTS neighbourhoods (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    borough TEXT NOT NULL,
    postcode_prefixes TEXT NOT NULL DEFAULT '[]', -- JSON
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]', -- JSON
    ward_aliases TEXT NOT NULL DEFAULT '[]' -- JSON
);

CREATE TABLE IF NOT EXISTS venues (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    postcode TEXT,
    postcode_normalised TEXT GENERATED ALWAYS AS (COALESCE(UPPER(REPLACE(postcode, ' ', '')), '')) VIRTUAL,
    neighbourhood_id INTEGER REFERENCES neighbourhoods(id),
    lat REAL,
    lng REAL,
    website TEXT,
    source_url TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_venues_unique ON venues(LOWER(name), postcode_normalised);

CREATE TABLE IF NOT EXISTS artists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    bio TEXT,
    genres TEXT NOT NULL DEFAULT '[]', -- JSON
    external_url TEXT,
    last_enriched_at TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    stable_hash TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    date_start_utc TEXT NOT NULL,
    date_end_utc TEXT,
    genres TEXT NOT NULL DEFAULT '[]', -- JSON
    venue_id INTEGER REFERENCES venues(id),
    ticket_url TEXT,
    sources TEXT NOT NULL DEFAULT '[]', -- JSON
    source_urls TEXT NOT NULL DEFAULT '[]', -- JSON
    scraped_at_utc TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}' -- JSON
);

CREATE TABLE IF NOT EXISTS event_artists (
    event_id INTEGER REFERENCES events(id),
    artist_id INTEGER REFERENCES artists(id),
    PRIMARY KEY (event_id, artist_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    title,
    genres,
    artists_concat,
    content=events,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, title, genres, artists_concat)
    VALUES (new.id, new.title, new.genres, '');
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, genres, artists_concat)
    VALUES ('delete', old.id, old.title, old.genres, '');
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, title, genres, artists_concat)
    VALUES ('delete', old.id, old.title, old.genres, '');
    INSERT INTO events_fts(rowid, title, genres, artists_concat)
    VALUES (new.id, new.title, new.genres, '');
END;

CREATE TABLE IF NOT EXISTS kb_meta (
    source TEXT PRIMARY KEY,
    last_refreshed_at TEXT NOT NULL,
    last_error TEXT
);

-- NOTE: JSON file is authoritative for v1.0; this table reserved for future analytics
CREATE TABLE IF NOT EXISTS token_ledger (
    day TEXT PRIMARY KEY,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0
);
