.PHONY: up down build logs api-dev web-dev test migrate venv install-api install-web fmt clean

up:
	docker compose up --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

venv:
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r apps/api/requirements.txt

install-api: venv

install-web:
	cd apps/web && npm install

api-dev:
	./.venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head
	./.venv/bin/uvicorn apps.api.main:app --app-dir . --reload --port 8000

web-dev:
	cd apps/web && npm run dev

migrate:
	./.venv/bin/python -m alembic -c apps/api/alembic.ini upgrade head

migration:
	./.venv/bin/python -m alembic -c apps/api/alembic.ini revision --autogenerate -m "$(msg)"

test:
	./.venv/bin/python -m pytest -v

clean:
	rm -f storage/secureprint.db
	rm -rf storage/incoming/* storage/processing/* storage/sanitized/*
	find . -name "__pycache__" -not -path "./.venv/*" -not -path "*/node_modules/*" -exec rm -rf {} +
