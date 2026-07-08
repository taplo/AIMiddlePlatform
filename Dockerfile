FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv sync --no-dev

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv .venv
COPY config/ config/
COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
