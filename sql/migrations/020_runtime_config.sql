-- 020_runtime_config.sql
-- Runtime configuration table for cross-pod stability plane overrides.
-- Written by memory-steward-mcp, read by memory-router and memory-steward
-- on config reload cycle.

BEGIN;

CREATE TABLE IF NOT EXISTS runtime_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE runtime_config IS
    'Operator-managed runtime overrides. Written by Glass Pane MCP, '
    'polled by memory-router and memory-steward on reload cycle.';

-- Seed defaults so the table is never empty on first read
INSERT INTO runtime_config (key, value) VALUES
    ('MAX_CONTEXT_TOKENS', '128000'),
    ('FORCE_MODE',         ''),
    ('HYSTERESIS_WINDOW',  '8')
ON CONFLICT (key) DO NOTHING;

COMMIT;
