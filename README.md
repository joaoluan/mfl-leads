# mfl-leads

Esteira local de leads do MyFoodLink. Ver `docs/SPEC.md`.

## Uso

    uv sync
    make seed CSV=contatos.csv   # colunas: nome,telefone,categoria,bairro
    make export                  # data/export/leads-<data>.csv
    make test

Banco em `db/leads.db` (ou `MFL_DB`), logs em `logs/<job>.jsonl` (ou `MFL_LOGS`).

## WhatsApp (Evolution, só leitura)

    docker compose up -d                 # Evolution + Postgres (segredos no .env, ver .env.example)
    systemctl --user start mfl-webhook   # receptor (ops/mfl-webhook.service)
    uv run mfl evo-conectar              # abre o QR; ler em Aparelhos conectados
    uv run mfl evo-status
    uv run mfl grupos                    # nomes e tamanhos
    uv run mfl grupo-importar "Nome exato do grupo"

A Evolution não grava mensagens. O webhook só grava as de números que já são lead
(envio vira toque, resposta vira reply com sugestão de classificação, "SAIR" vira opt-out permanente).
Firewall: `sudo ufw allow in on mfl-evo to 172.31.250.1 port 8001 proto tcp`.

## UI

    systemctl --user start mfl-ui        # http://127.0.0.1:8000 (ops/mfl-ui.service)
    uv run mfl marcar 51999990000 cliente

Telas: fila do dia, ficha (/lead/<id>), respostas, painel e config (tetos, pesos e textos em `cfg/`).

## iFood

Maps e iFood rodam juntos no timer das **01h30** (`mfl maps-noturno`): até 12 bairros,
sem iniciar etapa nova depois das 04h.
Por bairro, o Maps faz a coleta geral; o iFood usa um endereço comercial já coletado no bairro para descobrir outras lojas;
o Maps busca pelo nome/cidade as descobertas sem telefone, em lotes de 10 e até 30 nomes por noite.
Lote que esgota os 5 minutos salva o parcial e deixa as pendências para amanhã, sem falhar a rotina.
Instagram roda às 04h e score/backup às 05h.
Cada fonte tem sua data de visita: o iFood também roda nos bairros onde o Maps já está em dia e revisita após 60 dias.
Sem endereço comercial válido, o bairro fica pendente no iFood, com aviso no log.

Em **Coleta → iFood**, informe rua, número e cidade de um ponto de entrega comercial e clique em **Coletar iFood**.
Também pelo terminal, com o camofox-browser em `127.0.0.1:9377`:

    uv run mfl ifood "Rua, número, cidade - RS" --limite 30

Visita até 30 lojas por padrão (limite ajustável de 1 a 1000), priorizando novas, e marca `vende_ifood`.
Abre “Ver mais” para ler endereço, bairro, CEP e CNPJ no painel Sobre. Repetir a coleta completa as lojas antigas sem duplicar;
leituras parciais preservam os dados já conhecidos. Sem bloqueio, as vagas restantes completam lojas antigas, com 7 dias entre tentativas.
Depois de 403, painel vazio ou tempo esgotado nos detalhes, grava a suspensão no banco: os próximos bairros/processos continuam
descobrindo lojas novas e não abrem nenhuma loja para detalhes. A tela Coleta mostra a suspensão. Resolva o acesso antes de retomar explicitamente:

    uv run mfl ifood "Rua, número, cidade - RS" --retomar-detalhes

Não há retomada automática dos detalhes. A data de leitura fica em `detalhes_em`; regravar só esse metadado não conta como dado atualizado.
Veja o resultado em **Leads → Veio de → iFood**. Sem telefone, a casa aguarda Maps/Instagram.
Nome parecido sem endereço suficiente vai para **Revisão**. Um link do Maps com o UUID exato da loja no iFood confirma o vínculo,
mesmo se o iFood esconder o endereço. Buscas sem resultado suficiente voltam após 7 dias; falhas de execução, no dia seguinte.
O iFood pode bloquear detalhes ou a coleta: o log e a situação aparecem em Coleta. Uma fonte com erro não impede a outra de coletar.
