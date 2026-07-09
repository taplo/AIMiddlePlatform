FROM python:3.12-slim

WORKDIR /app
COPY .venv/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY config/ config/
COPY src/ src/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
