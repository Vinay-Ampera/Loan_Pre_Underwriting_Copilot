# Simple shortcuts. Run `make help` to list them.
# Each target calls .venv/bin directly, so no "activate" step is needed
# (a make recipe cannot keep an activated shell between commands).

VENV := .venv/bin

OBS := docker compose -f ops/docker-compose.observability.yml

.PHONY: help setup migrate backend frontend test test-fe lint grafana grafana-down grafana-logs up down stack-logs

help:
	@echo "make setup     - create .venv, install Python and npm packages"
	@echo "make migrate   - apply database migrations"
	@echo "make backend   - run the API (uvicorn, reload)"
	@echo "make frontend  - run the React dev server"
	@echo "make test      - run backend tests (pytest)"
	@echo "make test-fe   - run frontend tests"
	@echo "make lint      - ruff + mypy"
	@echo "make grafana      - start Grafana, Prometheus, Loki, Tempo (Grafana: http://localhost:3000, admin/admin)"
	@echo "make grafana-down - stop that stack"
	@echo "make grafana-logs - follow the stack's container logs"
	@echo "make up        - the whole stack in Docker (app http://localhost:8000, Grafana :3000)"
	@echo "make down      - stop the Docker stack (data volumes are kept)"
	@echo "make stack-logs - follow the Docker stack's logs"

setup:
	virtualenv .venv
	$(VENV)/pip install -r requirements.txt
	$(VENV)/pip install -e .
	cd frontend && npm install

migrate:
	$(VENV)/python -m app.db.migrate

# --host 0.0.0.0 lets the Prometheus container reach /metrics (it calls host.docker.internal).
# Synthetic data only; on a shared network use --host 127.0.0.1 and skip Grafana.
backend:
	cd backend && ../$(VENV)/uvicorn app.main:app --reload --host 0.0.0.0

frontend:
	cd frontend && npm run dev

test:
	$(VENV)/pytest -q

test-fe:
	cd frontend && npm test

lint:
	$(VENV)/ruff check . && $(VENV)/ruff format --check . && $(VENV)/mypy

# Observability stack (needs Docker). The API runs on the host: `make backend` in another terminal.
# For Tempo traces, set OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 in .env first.
grafana:
	$(OBS) up -d
	@echo "Grafana    http://localhost:3000  (s / s, or GRAFANA_ADMIN_PASSWORD)"
	@echo "Prometheus http://localhost:9090"

grafana-down:
	$(OBS) down

grafana-logs:
	$(OBS) logs -f

# The whole stack in Docker (Stage 11, docker-compose.yml). Only .env needs filling in.
up:
	docker compose up -d --build
	@echo "App        http://localhost:8000"
	@echo "Grafana    http://localhost:3000"

down:
	docker compose down

stack-logs:
	docker compose logs -f
