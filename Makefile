.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install backend frontend lint format typecheck test check up down

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install: ## Install backend and frontend dependencies
	cd backend && $(PY) -m pip install -r requirements-dev.txt
	cd frontend && npm ci

backend: ## Run the API with auto-reload on :8000
	cd backend && $(PY) -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend: ## Run the Vite dev server on :5173
	cd frontend && npm run dev

lint: ## Ruff + oxlint
	cd backend && ruff check .
	cd frontend && npm run lint

format: ## Auto-format the backend
	cd backend && ruff format . && ruff check . --fix

typecheck: ## mypy + tsc
	cd backend && mypy .
	cd frontend && npm run typecheck

test: ## pytest (with coverage gate) + vitest
	cd backend && pytest -q --cov --cov-fail-under=70
	cd frontend && npm test

check: lint typecheck test ## Everything CI runs

up: ## Build and start the stack in Docker (UI on http://127.0.0.1:8080)
	docker compose up --build -d

down: ## Stop the Docker stack
	docker compose down
