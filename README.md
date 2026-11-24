# mfl-leads

Esteira local de leads do MyFoodLink. Ver `docs/SPEC.md`.

## Uso

    uv sync
    make seed CSV=contatos.csv   # colunas: nome,telefone,categoria,bairro
    make export                  # data/export/leads-<data>.csv
    make test

Banco em `db/leads.db` (ou `MFL_DB`), logs em `logs/<job>.jsonl` (ou `MFL_LOGS`).
