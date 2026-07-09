FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir --proxy http://192.168.3.208:8787 .

COPY config/ config/
COPY src/ src/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
