-- Mantém ids, fontes antigas e índice durante a ampliação do CHECK
CREATE TABLE source_record_ifood (
  id INTEGER PRIMARY KEY, source TEXT CHECK(source IN ('cnpj','maps','instagram','grupo','ifood')),
  source_key TEXT NOT NULL, entity_id TEXT REFERENCES entity(entity_id),
  raw_json TEXT NOT NULL, url TEXT, captured_at TEXT NOT NULL, hash TEXT,
  match_score REAL, UNIQUE(source, source_key)
);
INSERT INTO source_record_ifood SELECT * FROM source_record;
DROP TABLE source_record;
ALTER TABLE source_record_ifood RENAME TO source_record;
CREATE INDEX source_record_entity ON source_record(entity_id);
