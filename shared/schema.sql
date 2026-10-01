-- Shared test schema, mounted into both experiment stacks' Postgres containers.
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
