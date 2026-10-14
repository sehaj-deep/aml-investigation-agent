# Project image: Python runtime with locked dependencies. Data is mounted, never copied.
FROM python:3.12.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

COPY pyproject.toml README.md ./
COPY aml_agent ./aml_agent
COPY scripts ./scripts
# Alert inputs only; ground truth is excluded by .dockerignore and must never be in an image.
COPY evals/alerts ./evals/alerts
RUN pip install --no-cache-dir --no-deps .

RUN useradd --create-home --uid 10001 app
USER app
