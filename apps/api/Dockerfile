FROM python:3.11-slim

WORKDIR /repo

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt /repo/apps/api/requirements.txt
RUN pip install --no-cache-dir -r /repo/apps/api/requirements.txt

COPY apps/api /repo/apps/api
COPY apps/__init__.py /repo/apps/__init__.py
COPY services /repo/services
COPY config /repo/config

RUN mkdir -p /repo/storage/incoming /repo/storage/processing /repo/storage/sanitized

ENV PYTHONPATH=/repo
WORKDIR /repo

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic -c apps/api/alembic.ini upgrade head && uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]
