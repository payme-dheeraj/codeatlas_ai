# CodeAtlas AI — Developer Makefile
# Usage: make <target>

.DEFAULT_GOAL := help
DOCKER_COMPOSE := docker compose -f docker/docker-compose.yml
BACKEND_DIR    := backend

# ── Help ──────────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ── Docker ────────────────────────────────────────────────────────────────────

.PHONY: up
up: ## Start all core services (gateway, frontend, backend, worker + infra)
	$(DOCKER_COMPOSE) --profile core up -d

.PHONY: up-ai
up-ai: ## Start core + Ollama AI runtime (requires GPU for best performance)
	$(DOCKER_COMPOSE) --profile core --profile ai up -d

.PHONY: up-monitoring
up-monitoring: ## Start core + Prometheus + Grafana
	$(DOCKER_COMPOSE) --profile core --profile monitoring up -d

.PHONY: up-all
up-all: ## Start everything (core + ai + monitoring)
	$(DOCKER_COMPOSE) --profile core --profile ai --profile monitoring up -d

.PHONY: down
down: ## Stop all running containers
	$(DOCKER_COMPOSE) down

.PHONY: down-volumes
down-volumes: ## Stop all containers AND remove all volumes (DESTRUCTIVE)
	$(DOCKER_COMPOSE) down -v

.PHONY: restart
restart: ## Restart all services
	$(DOCKER_COMPOSE) restart

.PHONY: logs
logs: ## Tail logs for all services
	$(DOCKER_COMPOSE) logs -f

.PHONY: logs-backend
logs-backend: ## Tail backend logs
	$(DOCKER_COMPOSE) logs -f backend

.PHONY: logs-worker
logs-worker: ## Tail worker logs
	$(DOCKER_COMPOSE) logs -f worker

.PHONY: ps
ps: ## Show service status
	$(DOCKER_COMPOSE) ps

.PHONY: build
build: ## Rebuild backend + worker Docker images
	$(DOCKER_COMPOSE) --profile core build backend worker

.PHONY: build-frontend
build-frontend: ## Rebuild frontend Docker image
	$(DOCKER_COMPOSE) --profile core build frontend

.PHONY: build-all
build-all: ## Rebuild all images
	$(DOCKER_COMPOSE) --profile core build

.PHONY: scale-worker
scale-worker: ## Scale worker to N instances (make scale-worker N=4)
	$(DOCKER_COMPOSE) up -d --scale worker=$(N)

# ── Database ──────────────────────────────────────────────────────────────────

.PHONY: migrate
migrate: ## Run Alembic migrations inside the backend container
	$(DOCKER_COMPOSE) exec backend alembic upgrade head

.PHONY: migrate-local
migrate-local: ## Run Alembic migrations locally (requires .env)
	cd $(BACKEND_DIR) && alembic upgrade head

.PHONY: migration
migration: ## Create a new Alembic migration (make migration MSG="add_foo")
	cd $(BACKEND_DIR) && alembic revision --autogenerate -m "$(MSG)"

.PHONY: db-shell
db-shell: ## Open psql shell in the postgres container
	$(DOCKER_COMPOSE) exec postgres psql -U codeatlas -d codeatlas

# ── Ollama ────────────────────────────────────────────────────────────────────

.PHONY: pull-models
pull-models: ## Pull default Ollama models (llama3.2 + nomic-embed-text)
	$(DOCKER_COMPOSE) exec ollama ollama pull llama3.2
	$(DOCKER_COMPOSE) exec ollama ollama pull nomic-embed-text

# ── Development ───────────────────────────────────────────────────────────────

.PHONY: dev
dev: ## Start backend in dev mode with hot-reload (local)
	cd $(BACKEND_DIR) && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

.PHONY: dev-frontend
dev-frontend: ## Start frontend in dev mode (local)
	cd frontend && npm run dev

.PHONY: install
install: ## Install backend dependencies locally
	cd $(BACKEND_DIR) && pip install -e ".[dev]"

.PHONY: install-frontend
install-frontend: ## Install frontend npm dependencies
	cd frontend && npm install

.PHONY: test
test: ## Run all tests
	cd $(BACKEND_DIR) && pytest -v

.PHONY: test-unit
test-unit: ## Run unit tests only
	cd $(BACKEND_DIR) && pytest tests/unit/ -v

.PHONY: test-integration
test-integration: ## Run integration tests only
	cd $(BACKEND_DIR) && pytest tests/integration/ -v

.PHONY: lint
lint: ## Run ruff linter
	cd $(BACKEND_DIR) && ruff check .

.PHONY: format
format: ## Format code with ruff
	cd $(BACKEND_DIR) && ruff format .

.PHONY: typecheck
typecheck: ## Run mypy type checker
	cd $(BACKEND_DIR) && mypy app/

# ── Env ───────────────────────────────────────────────────────────────────────

.PHONY: env
env: ## Copy root .env.example to .env (skips if .env already exists)
	@if [ ! -f .env ]; then cp .env.example .env && echo ".env created from .env.example"; \
	  else echo ".env already exists — skipping"; fi

.PHONY: env-backend
env-backend: ## Copy backend/.env.example to backend/.env
	@if [ ! -f $(BACKEND_DIR)/.env ]; then cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env && echo "backend/.env created"; \
	  else echo "backend/.env already exists — skipping"; fi

.PHONY: env-frontend
env-frontend: ## Copy frontend/.env.example to frontend/.env.local
	@if [ ! -f frontend/.env.local ]; then cp frontend/.env.example frontend/.env.local && echo "frontend/.env.local created"; \
	  else echo "frontend/.env.local already exists — skipping"; fi

.PHONY: env-all
env-all: env env-backend env-frontend ## Copy all .env.example files
