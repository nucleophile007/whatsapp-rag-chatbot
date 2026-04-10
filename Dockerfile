FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-compile -r /app/requirements.txt \
    && find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} +

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app app

COPY --from=builder /opt/venv /opt/venv

# Copy only runtime source files needed by server + worker.
COPY *.py /app/
COPY queues /app/queues
COPY database /app/database
COPY client /app/client
COPY run_worker.sh /app/run_worker.sh

RUN chmod +x /app/run_worker.sh \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Default command (overridden in docker-compose for server/worker).
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
