PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS entity (
  entity_id TEXT PRIMARY KEY, cnpj TEXT UNIQUE, place_id TEXT UNIQUE,
  ig_username TEXT UNIQUE, nome TEXT, fantasia TEXT, cnae TEXT, categoria TEXT, uf TEXT,
  municipio TEXT, bairro TEXT, cep TEXT, endereco TEXT, tel1 TEXT, tel2 TEXT,
  email TEXT, site TEXT, nota REAL, avaliacoes INTEGER, sinais TEXT,
  score REAL DEFAULT 0, status TEXT DEFAULT 'novo',
  opt_out INTEGER DEFAULT 0, motivo_descarte TEXT,
  criado_em TEXT, atualizado_em TEXT
);
CREATE INDEX IF NOT EXISTS entity_tel1 ON entity(tel1);

CREATE TABLE IF NOT EXISTS source_record (
  id INTEGER PRIMARY KEY, source TEXT CHECK(source IN ('cnpj','maps','instagram','grupo')),
  source_key TEXT NOT NULL, entity_id TEXT REFERENCES entity(entity_id),
  raw_json TEXT NOT NULL, url TEXT, captured_at TEXT NOT NULL, hash TEXT,
  match_score REAL, UNIQUE(source, source_key)
);

CREATE TABLE IF NOT EXISTS touch (
  id INTEGER PRIMARY KEY, entity_id TEXT REFERENCES entity(entity_id),
  canal TEXT CHECK(canal IN ('whatsapp','instagram')),
  template_id TEXT, texto TEXT NOT NULL, enviado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reply (
  id INTEGER PRIMARY KEY, entity_id TEXT REFERENCES entity(entity_id),
  texto TEXT, classificacao TEXT CHECK(classificacao IN
    ('interesse','preco','ja_tenho','nao','opt_out')), recebido_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS validacao (
  telefone TEXT PRIMARY KEY, resultado TEXT, verificado_em TEXT
);

CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY, entity_id TEXT REFERENCES entity(entity_id),
  kind TEXT NOT NULL, tries INTEGER DEFAULT 0, next_at TEXT, done INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS revisao (
  id INTEGER PRIMARY KEY, a TEXT, b TEXT, score REAL, decidido INTEGER DEFAULT 0
);
