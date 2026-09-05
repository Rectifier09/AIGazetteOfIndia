-- ingestion/migrations/001_init.sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE notifications (
    id                   SERIAL PRIMARY KEY,
    source               TEXT NOT NULL CHECK (source IN ('central', 'gujarat')),
    gazette_id           TEXT,
    gazette_type         TEXT,
    part                 TEXT,
    section              TEXT,
    issuing_authority    TEXT,
    notification_number  TEXT,
    notification_date    TEXT,
    act_reference        TEXT,
    signatory            TEXT,
    operative_text       TEXT NOT NULL,
    source_url           TEXT,
    file_hash            TEXT NOT NULL,
    embedding            vector(768),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, gazette_id, file_hash)
);

CREATE TABLE relationships (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    rel_type          TEXT NOT NULL CHECK (rel_type IN ('issued_under', 'supersedes', 'amends')),
    target            TEXT NOT NULL
);

CREATE INDEX notifications_fts_idx ON notifications
    USING GIN (to_tsvector('english', operative_text || ' ' || coalesce(act_reference, '')));

CREATE INDEX relationships_target_idx ON relationships (target);
