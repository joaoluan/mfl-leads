.PHONY: seed export test etl icp

seed:
	@test -n "$(CSV)" || (echo "uso: make seed CSV=arquivo.csv" >&2; exit 2)
	uv run mfl seed "$(CSV)"

export:
	uv run mfl export

test:
	uv run pytest -q

etl:
	@test -n "$(MES)" || (echo "uso: make etl MES=AAAA-MM" >&2; exit 2)
	uv run mfl cnpj-baixar "$(MES)" && uv run mfl cnpj-etl "$(MES)"

icp:
	uv run mfl cnpj-icp
