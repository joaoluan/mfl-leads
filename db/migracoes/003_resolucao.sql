-- Fase 5: bloqueio da resolução por CEP e telefone secundário (CNPJ)
CREATE INDEX entity_cep ON entity(cep);
CREATE INDEX entity_tel2 ON entity(tel2);
CREATE INDEX revisao_pendente ON revisao(decidido)
