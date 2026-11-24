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
