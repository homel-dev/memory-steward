-- 040_git_connections.sql
-- Named Git repository connections (GitLab, GitHub, Bitbucket).
-- Replaces gitlab_connections. Managed by Glass Pane MCP (git_plane).

BEGIN;

CREATE TABLE IF NOT EXISTS git_connections (
    name          TEXT PRIMARY KEY,
    provider      TEXT NOT NULL
                  CHECK (provider IN ('gitlab', 'github', 'bitbucket')),
    base_url      TEXT NOT NULL,
    token         TEXT NOT NULL,
    access_level  TEXT NOT NULL DEFAULT 'read'
                  CHECK (access_level IN ('read', 'read-write')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE git_connections IS
    'Named Git provider connections (GitLab/GitHub/Bitbucket). '
    'Managed by Glass Pane MCP git_plane. '
    'access_level: read = ingest only, read-write = ingest + write files.';

COMMIT;
