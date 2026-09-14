-- 050_builder_runtime_config.sql
-- Make the Builder endpoint switchable at runtime via the runtime_config table,
-- picked up by memory-router within RUNTIME_CONFIG_TTL_SECONDS (no pod restart).
--
-- Behavior-neutral on apply: seeds BUILDER_BASE_URL to the current ConfigMap
-- default, and does NOT seed BUILDER_MODEL (so the import-time env value keeps
-- winning). Applying this file changes nothing until you run a switch below.

BEGIN;

-- Live Builder endpoint. ON CONFLICT DO NOTHING => never clobbers an existing
-- operator override on re-apply.
INSERT INTO runtime_config (key, value) VALUES
    ('BUILDER_BASE_URL', 'https://api.openai.com/v1')
ON CONFLICT (key) DO NOTHING;

COMMIT;

-- ---------------------------------------------------------------------------
-- Operator switches. Run manually; effect lands within the TTL, no restart.
-- ALWAYS set BOTH keys together so the model id matches the endpoint, or the
-- builder 404s on a model it doesn't serve.
-- ---------------------------------------------------------------------------

-- Switch the Builder to the local vLLM instance:
-- INSERT INTO runtime_config (key, value) VALUES
--     ('BUILDER_BASE_URL', 'http://vllm-builder:8000/v1'),
--     ('BUILDER_MODEL',    'Qwen/Qwen2.5-32B-Instruct-AWQ')
-- ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now();

-- Switch back to OpenAI (set BUILDER_MODEL to your actual OpenAI model id):
-- INSERT INTO runtime_config (key, value) VALUES
--     ('BUILDER_BASE_URL', 'https://api.openai.com/v1'),
--     ('BUILDER_MODEL',    'gpt-4o')
-- ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now();

-- Inspect current live values:
-- SELECT key, value, updated_at FROM runtime_config
--  WHERE key IN ('BUILDER_BASE_URL', 'BUILDER_MODEL');
