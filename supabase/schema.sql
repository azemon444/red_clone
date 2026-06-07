-- Run once in Supabase → SQL Editor (optional; the app creates this automatically on first start)
CREATE TABLE IF NOT EXISTS datasets (
  key TEXT PRIMARY KEY,
  data JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
