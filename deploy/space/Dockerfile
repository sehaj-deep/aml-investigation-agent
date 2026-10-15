# Public demo: the whole stack in one container, for a free container host (Render's
# free web service; also runs on Hugging Face Spaces or Cloud Run). Built by
# scripts/build_space.py, which assembles this folder with the code, the data slice and
# the demo database.

FROM node:22.12-alpine AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
# Postgres 17 with pgvector from the PostgreSQL project's apt repository, and nginx.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg nginx \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-17 postgresql-17-pgvector \
 && rm -rf /var/lib/apt/lists/*

# Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY --chown=user aml_agent/ aml_agent/
COPY --chown=user space/ space/
COPY --chown=user data/ data/
COPY --chown=user --from=ui /ui/dist ui/

ENV PYTHONPATH=/app \
    PARQUET_DIR=/app/data/parquet \
    ALERT_QUEUE_DIR=/app/data/alert_queue \
    POSTGRES_HOST=127.0.0.1 \
    POSTGRES_PORT=5432 \
    POSTGRES_USER=aml \
    POSTGRES_DB=aml \
    MCP_HOST=127.0.0.1 \
    MCP_PORT=8001 \
    MCP_URL=http://127.0.0.1:8001/mcp \
    API_HOST=127.0.0.1 \
    API_PORT=8000 \
    LLM_PROVIDER=ollama \
    LLM_MODEL=gpt-oss:20b \
    OLLAMA_BASE_URL=https://ollama.com \
    DEMO_MODE=true \
    GUIDANCE_SEARCH=keyword

USER user
EXPOSE 7860
CMD ["bash", "space/start.sh"]
