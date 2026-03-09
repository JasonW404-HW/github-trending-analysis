-- PostgreSQL schema setup for github-trending-analysis
-- Run as gh_analyzer after postgres_init.sql:
--   psql -h localhost -p 5432 -U gh_analyzer -d github_trend_analysis -f scripts/sql/postgres_schema.sql

CREATE TABLE IF NOT EXISTS repos_daily (
    id BIGSERIAL PRIMARY KEY,
    date DATE NOT NULL,
    rank INTEGER NOT NULL,
    repo_name TEXT NOT NULL,
    owner TEXT NOT NULL,
    stars INTEGER NOT NULL,
    stars_delta INTEGER DEFAULT 0,
    forks INTEGER,
    issues INTEGER,
    language TEXT,
    url TEXT,
    repo_updated_at TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(date, repo_name)
);

CREATE TABLE IF NOT EXISTS repos_details (
    id BIGSERIAL PRIMARY KEY,
    repo_name TEXT UNIQUE NOT NULL,
    summary TEXT NOT NULL,
    description TEXT,
    use_case TEXT,
    solves TEXT,
    tags TEXT,
    purpose_assessment TEXT,
    category TEXT NOT NULL,
    category_zh TEXT NOT NULL,
    topics TEXT,
    language TEXT,
    readme_summary TEXT,
    owner TEXT NOT NULL,
    url TEXT NOT NULL,
    repo_updated_at TEXT,
    prompt_hash TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS repos_history (
    id BIGSERIAL PRIMARY KEY,
    repo_name TEXT NOT NULL,
    date DATE NOT NULL,
    rank INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    forks INTEGER,
    UNIQUE(repo_name, date)
);

CREATE TABLE IF NOT EXISTS github_fetch_state (
    request_key TEXT PRIMARY KEY,
    etag TEXT,
    last_checked_at TEXT,
    last_success_at TEXT,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE repos_daily ADD COLUMN IF NOT EXISTS repo_updated_at TEXT;
ALTER TABLE repos_details ADD COLUMN IF NOT EXISTS repo_updated_at TEXT;
ALTER TABLE repos_details ADD COLUMN IF NOT EXISTS tags TEXT;
ALTER TABLE repos_details ADD COLUMN IF NOT EXISTS prompt_hash TEXT;
ALTER TABLE repos_details ADD COLUMN IF NOT EXISTS purpose_assessment TEXT;

CREATE INDEX IF NOT EXISTS idx_daily_date ON repos_daily(date);
CREATE INDEX IF NOT EXISTS idx_daily_repo ON repos_daily(repo_name);
CREATE INDEX IF NOT EXISTS idx_daily_rank ON repos_daily(date, rank);
CREATE INDEX IF NOT EXISTS idx_details_category ON repos_details(category);
CREATE INDEX IF NOT EXISTS idx_details_owner ON repos_details(owner);
CREATE INDEX IF NOT EXISTS idx_details_language ON repos_details(language);
CREATE INDEX IF NOT EXISTS idx_history_repo ON repos_history(repo_name);
CREATE INDEX IF NOT EXISTS idx_history_date ON repos_history(date);
