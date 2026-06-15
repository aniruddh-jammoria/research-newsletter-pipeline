CREATE TABLE IF NOT EXISTS runs (
    run_id        TEXT PRIMARY KEY,
    started_at    TEXT NOT NULL,
    completed_at  TEXT,
    status        TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    num_queries   INTEGER,
    article_count INTEGER,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL,
    error_message TEXT
);
