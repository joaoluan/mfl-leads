.PHONY: seed export test

seed:
	@test -n "$(CSV)" || (echo "uso: make seed CSV=arquivo.csv" >&2; exit 2)
	uv run mfl seed "$(CSV)"

export:
	uv run mfl export

test:
	uv run pytest -q
