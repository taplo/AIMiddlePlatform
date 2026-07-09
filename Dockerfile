FROM python:3.14-slim

WORKDIR /app
COPY requirements.txt .
COPY wheelhouse/ /wheelhouse/
RUN pip install --no-index --find-links /wheelhouse setuptools && \
    pip install --no-index --find-links /wheelhouse -r requirements.txt

COPY config/ config/
COPY src/ src/

ENV PYTHONPATH="/app" \
    APP_ENV="production"

EXPOSE 8000

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
