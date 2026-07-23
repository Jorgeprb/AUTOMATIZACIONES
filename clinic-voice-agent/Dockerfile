FROM python:3.12-slim AS builder

ARG INSTALL_DEV=false
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip install --no-cache-dir --upgrade pip build \
    && if [ "$INSTALL_DEV" = "true" ]; then \
         python -m pip wheel --no-cache-dir --wheel-dir /wheels ".[dev]"; \
       else \
         python -m pip wheel --no-cache-dir --wheel-dir /wheels .; \
       fi

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/*.whl \
    && rm -rf /wheels \
    && addgroup --system clinic \
    && adduser --system --ingroup clinic --home /app clinic
COPY alembic ./alembic
COPY alembic.ini Makefile ./
COPY scripts ./scripts
COPY tests ./tests
RUN chown -R clinic:clinic /app
USER clinic
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
