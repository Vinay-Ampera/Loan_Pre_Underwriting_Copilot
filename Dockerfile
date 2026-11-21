# syntax=docker/dockerfile:1
# Pramaan (Stage 11): one image with the API, the graph runner and the built frontend.
# Exact Python versions come from requirements.lock; the local embedding, reranker and OCR models
# are loaded at build time, so a container never downloads a model. Secrets are never copied in
# (.dockerignore): the container reads them from .env at run time (docker-compose.yml).

# ---------------------------------------------------------------- the frontend
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- the app
FROM python:3.12-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/models/hf \
    OMP_NUM_THREADS=2
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 libgl1 curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

COPY requirements.lock ./
RUN pip install -r requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./
COPY backend/ backend/
COPY data/ data/
RUN pip install --no-deps -e .

# Synthetic data is not in git: make it here, the same way CI does (fixed seeds).
RUN python -m synthetic.generate --split all && python -m synthetic.verify

COPY docker/warm_models.py /tmp/warm_models.py
RUN python /tmp/warm_models.py && rm /tmp/warm_models.py && chmod -R a+rX /opt/models

COPY --from=web /web/dist frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/pramaan-entrypoint

RUN useradd --create-home --uid 10001 pramaan \
    && mkdir -p data/uploads logs \
    && chown -R pramaan:pramaan data/uploads logs
USER pramaan

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 UPLOAD_DIR=/app/data/uploads
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
ENTRYPOINT ["pramaan-entrypoint"]
# One worker: the graph runner keeps running cases in this process (no Celery, no Redis).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
