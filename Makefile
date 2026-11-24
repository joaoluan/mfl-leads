.PHONY: seed export test etl icp maps resolve score ig

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

maps:
	@test -n "$(BAIRRO)" || (echo "uso: make maps BAIRRO=moinhos-de-vento" >&2; exit 2)
	uv run mfl maps "$(BAIRRO)"

resolve:
	uv run mfl resolver

score:
	uv run mfl score

ig:
	uv run mfl ig-handles
	uv run mfl ig --limite $(or $(N),30)
