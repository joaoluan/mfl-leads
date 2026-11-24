-- Fase 2: idempotência por id da mensagem do WhatsApp, tiques, revisão e bloqueio permanente.
-- Sem ponto e vírgula dentro de comentários: o aplicador separa comandos por ele.
ALTER TABLE touch ADD COLUMN wa_msg_id TEXT;
ALTER TABLE touch ADD COLUMN ack TEXT;
ALTER TABLE touch ADD COLUMN ack_em TEXT;
CREATE UNIQUE INDEX touch_wa_msg_id ON touch(wa_msg_id);
ALTER TABLE reply ADD COLUMN wa_msg_id TEXT;
ALTER TABLE reply ADD COLUMN revisado INTEGER DEFAULT 0;
CREATE UNIQUE INDEX reply_wa_msg_id ON reply(wa_msg_id);
CREATE TABLE bloqueio (tel_hash TEXT PRIMARY KEY, motivo TEXT, criado_em TEXT NOT NULL);
CREATE TABLE estado (chave TEXT PRIMARY KEY, valor TEXT, atualizado_em TEXT NOT NULL);
