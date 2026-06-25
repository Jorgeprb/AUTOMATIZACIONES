FROM python:3.12-slim

ARG INSTALL_DEV=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl make \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir ".[dev]"; \
    else \
        pip install --no-cache-dir "."; \
    fi

COPY alembic ./alembic
COPY alembic.ini Makefile ./
COPY scripts ./scripts
COPY tests ./tests

RUN addgroup --system clinic \
    && adduser --system --ingroup clinic --home /app clinic \
    && chown -R clinic:clinic /app

USER clinic

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
