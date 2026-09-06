-- ingestion/migrations/002_chunking.sql
ALTER TABLE notifications DROP COLUMN embedding;
DROP INDEX IF EXISTS notifications_fts_idx;

CREATE TABLE notification_chunks (
    id                SERIAL PRIMARY KEY,
    notification_id   INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    chunk_index       INTEGER NOT NULL,
    chunk_text        TEXT NOT NULL,
    embedding         vector(768) NOT NULL,
    UNIQUE (notification_id, chunk_index)
);

CREATE INDEX notification_chunks_fts_idx ON notification_chunks
    USING GIN (to_tsvector('english', chunk_text));
