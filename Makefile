.PHONY: up down test test-integration eval lint reindex

up:
	docker compose up --build

down:
	docker compose down

test:
	cd backend && python -m pytest -m unit
	cd frontend && npm test

test-integration:
	docker compose up -d qdrant
	cd backend && python -m pytest -m integration

eval:
	cd backend && python -m app.evaluation --dataset eval/dataset.yaml --output eval-report.json

lint:
	cd backend && ruff check . && ruff format --check .
	cd frontend && npm run lint && npm run build

reindex:
	curl -fsS -X POST http://localhost:8000/api/v1/index/reindex
