FROM python:3.12-slim

ARG http_proxy
ARG https_proxy
ARG HTTP_PROXY
ARG HTTPS_PROXY

WORKDIR /app
COPY pyproject.toml .
RUN echo "http_proxy=$http_proxy" && \
    if [ -n "$http_proxy" ]; then \
      export http_proxy=$http_proxy https_proxy=$https_proxy HTTP_PROXY=$http_proxy HTTPS_PROXY=$https_proxy; \
    fi && \
    pip install --no-cache-dir setuptools && \
    pip install --no-cache-dir .

COPY config/ config/
COPY src/ src/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
