# Simple shortcuts. Run `make help` to list them.
# Each target calls .venv/bin directly, so no "activate" step is needed
# (a make recipe cannot keep an activated shell between commands).

VENV := .venv/bin

.PHONY: help setup migrate backend frontend test test-fe lint

help:
	@echo "make setup     - create .venv, install Python and npm packages"
	@echo "make migrate   - apply database migrations"
	@echo "make backend   - run the API (uvicorn, reload)"
	@echo "make frontend  - run the React dev server"
	@echo "make test      - run backend tests (pytest)"
	@echo "make test-fe   - run frontend tests"
	@echo "make lint      - ruff + mypy"

setup:
	virtualenv .venv
	$(VENV)/pip install -r requirements.txt
	$(VENV)/pip install -e .
	cd frontend && npm install

migrate:
	$(VENV)/python -m app.db.migrate

backend:
	cd backend && ../$(VENV)/uvicorn app.main:app --reload

frontend:
	cd frontend && npm run dev

test:
	$(VENV)/pytest -q

test-fe:
	cd frontend && npm test

lint:
	$(VENV)/ruff check . && $(VENV)/ruff format --check . && $(VENV)/mypy
