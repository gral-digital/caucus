.PHONY: help install up down dev migrate seed-codice-civile seed-codice-penale lint test clean

help:  ## Mostra questo aiuto
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-24s\033[0m %s\n", $$1, $$2}'

install:  ## Installa tutte le dipendenze (Python via uv, Node via pnpm)
	uv sync --all-packages
	pnpm install

up:  ## Avvia infra locale (Postgres, Qdrant, Redis, Langfuse)
	docker compose up -d
	@echo "Postgres:  localhost:5432  (user=avvocato db=avvocato)"
	@echo "Qdrant:    http://localhost:6333/dashboard"
	@echo "Redis:     localhost:6379"
	@echo "Langfuse:  http://localhost:3001"

down:  ## Ferma infra locale
	docker compose down

dev:  ## Avvia API + Web in modalità dev (parallelo)
	pnpm turbo run dev --parallel

dev-api:  ## Solo API
	cd apps/api && uv run uvicorn avvocato_api.main:app --reload --port 8000

dev-web:  ## Solo frontend
	pnpm --filter @avvocato/web dev

migrate:  ## Applica migration Postgres
	cd apps/api && uv run alembic upgrade head

migrate-new:  ## Crea nuova migration (usage: make migrate-new msg="descrizione")
	cd apps/api && uv run alembic revision --autogenerate -m "$(msg)"

fetch-codici:  ## Scarica AKN XML di CC + CP e salva come fixture (richiede rete)
	uv run avvocato-ingest fetch --codice cc
	uv run avvocato-ingest fetch --codice cp

seed-codice-civile:  ## Indicizza Codice Civile (usa fixture se presente, altrimenti scarica)
	uv run avvocato-ingest ingest --codice cc --from-fixture

seed-codice-penale:  ## Indicizza Codice Penale (usa fixture se presente, altrimenti scarica)
	uv run avvocato-ingest ingest --codice cp --from-fixture

seed-codici-fast:  ## Indicizza entrambi i codici SENZA embeddings (Postgres-only, 10× più veloce)
	uv run avvocato-ingest ingest --codice cc --from-fixture --skip-embeddings
	uv run avvocato-ingest ingest --codice cp --from-fixture --skip-embeddings

parse-codici:  ## Parse-only (nessuna persistenza); verifica conteggio articoli
	uv run avvocato-ingest parse --codice cc
	uv run avvocato-ingest parse --codice cp

lint:  ## Lint (Python + TS)
	uv run ruff check .
	uv run ruff format --check .
	pnpm turbo run lint

fix:  ## Auto-fix lint
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy apps services
	pnpm turbo run typecheck

test:
	uv run pytest
	pnpm turbo run test

clean:
	docker compose down -v
	rm -rf .venv node_modules .turbo apps/*/.next
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
