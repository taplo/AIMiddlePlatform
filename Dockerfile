FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=300 -r requirements.txt

COPY config/ config/
COPY src/ src/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
