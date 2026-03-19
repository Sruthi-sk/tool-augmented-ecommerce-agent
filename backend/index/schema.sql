-- Pre-indexed structured truth store (SQLite)
-- This schema is used by ingestion scripts to build deterministic product facts.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS parts (
  part_number TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  price TEXT,
  in_stock INTEGER,
  description TEXT,
  manufacturer_part_number TEXT,
  source_url TEXT,
  updated_at REAL,
  brand TEXT,
  availability TEXT,
  appliance_type TEXT,
  install_difficulty TEXT,
  install_time TEXT,
  replace_parts TEXT,
  symptoms_text TEXT,
  repair_rating TEXT
);

CREATE TABLE IF NOT EXISTS models (
  model_number TEXT PRIMARY KEY,
  brand TEXT,
  appliance_type TEXT,
  updated_at REAL
);

CREATE TABLE IF NOT EXISTS part_compatibility (
  part_number TEXT NOT NULL,
  model_number TEXT NOT NULL,
  evidence_url TEXT,
  updated_at REAL,
  PRIMARY KEY (part_number, model_number),
  FOREIGN KEY (part_number) REFERENCES parts(part_number) ON DELETE CASCADE,
  FOREIGN KEY (model_number) REFERENCES models(model_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS part_installation_steps (
  part_number TEXT NOT NULL,
  step_index INTEGER NOT NULL,
  step_text TEXT NOT NULL,
  evidence_url TEXT,
  updated_at REAL,
  PRIMARY KEY (part_number, step_index),
  FOREIGN KEY (part_number) REFERENCES parts(part_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS part_symptoms (
  part_number TEXT NOT NULL,
  symptom_key TEXT NOT NULL,
  evidence_url TEXT,
  updated_at REAL,
  PRIMARY KEY (part_number, symptom_key),
  FOREIGN KEY (part_number) REFERENCES parts(part_number) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS troubleshooting_causes (
  appliance_type TEXT NOT NULL,
  symptom_key TEXT NOT NULL,
  likely_cause_text TEXT NOT NULL,
  recommended_part_number TEXT,
  part_type TEXT,
  likelihood TEXT,
  evidence_url TEXT,
  updated_at REAL,
  PRIMARY KEY (appliance_type, symptom_key, likely_cause_text),
  FOREIGN KEY (recommended_part_number) REFERENCES parts(part_number) ON DELETE SET NULL
);

-- Semantic/help augmentation storage:
-- FAISS embeddings may live outside SQLite; this table stores chunk metadata (and chunk_text for fallback retrieval).
CREATE TABLE IF NOT EXISTS help_chunks (
  chunk_id TEXT PRIMARY KEY,
  appliance_type TEXT,
  help_type TEXT,
  symptom_key TEXT,
  source_url TEXT,
  chunk_text TEXT,
  updated_at REAL
);

-- Optional FTS for faster keyword-style search
CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts
USING fts5(
  part_number,
  name,
  description,
  content='',
  tokenize='porter'
);

CREATE VIRTUAL TABLE IF NOT EXISTS help_chunks_fts
USING fts5(
  chunk_id,
  chunk_text,
  content='',
  tokenize='porter'
);

