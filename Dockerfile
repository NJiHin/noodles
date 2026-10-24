# One image: the API and the built front end on :8000. Ollama runs on the host (see README).
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
# Java for OpenDataLoader, LibreOffice to convert .pptx/.docx, and fonts metric-compatible with Arial, Calibri and Cambria
RUN apt-get update && apt-get install -y --no-install-recommends \
      default-jre-headless libreoffice-writer-nogui libreoffice-impress-nogui \
      fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY noodles/ noodles/
COPY --from=web /app/frontend/dist frontend/dist
ENV NOODLES_STATIC=frontend/dist NOODLES_OLLAMA_URL=http://host.docker.internal:11434 PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "noodles.api:from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
