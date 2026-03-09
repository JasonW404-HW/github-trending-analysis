-- PostgreSQL initialization for github-trending-analysis
-- Run as a superuser (e.g. postgres):
--   psql -h localhost -p 5432 -U postgres -f scripts/sql/postgres_init.sql

DO
$$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gh_analyzer') THEN
        CREATE ROLE gh_analyzer LOGIN PASSWORD 'dev123dev321';
    ELSE
        ALTER ROLE gh_analyzer WITH LOGIN PASSWORD 'dev123dev321';
    END IF;
END
$$;

SELECT 'CREATE DATABASE github_trend_analysis OWNER gh_analyzer'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'github_trend_analysis'
)\gexec

GRANT ALL PRIVILEGES ON DATABASE github_trend_analysis TO gh_analyzer;
ALTER DATABASE github_trend_analysis OWNER TO gh_analyzer;
