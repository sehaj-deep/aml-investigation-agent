# Targets assume the venv at .venv is active (or PY points at its python).
PY ?= python

.PHONY: install lint test test-data convert alerts latency up down

install:
	$(PY) -m pip install -r requirements.txt -r requirements-dev.txt
	$(PY) -m pip install --no-deps -e .
	pre-commit install

lint:
	ruff check .
	ruff format --check .

test:
	$(PY) -m pytest -m "not data and not docker"

test-data:
	$(PY) -m pytest -m "data"

convert:
	$(PY) scripts/convert_to_parquet.py

alerts:
	$(PY) scripts/build_alerts.py

latency:
	docker compose --profile bench run --rm bench

up:
	docker compose up -d --wait

down:
	docker compose down
