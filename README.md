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

Em **Coleta → iFood**, informe rua, número e cidade de um ponto de entrega comercial e clique em **Coletar iFood**.
Também pelo terminal, com o camofox-browser em `127.0.0.1:9377`:

    uv run mfl ifood "Rua, número, cidade - RS" --limite 30

Coleta até 30 lojas novas (limite ajustável de 1 a 100), pula as já importadas e marca `vende_ifood`.
Veja o resultado em **Leads → Veio de → iFood**. Sem telefone, a casa aguarda Maps/Instagram.
Nome parecido sem endereço suficiente vai para **Revisão**; não vincula sozinho.
O iFood pode bloquear detalhes ou a coleta: o log e a situação aparecem em Coleta. Não há agendamento automático.
