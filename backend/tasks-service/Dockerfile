# syntax=docker/dockerfile:1.7
# Multi-stage build с uv. См. architecture.md §17.1.1.

FROM python:3.13-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /build

COPY pyproject.toml ./
COPY src ./src

RUN uv venv /opt/venv && \
    uv pip install --no-cache --python /opt/venv/bin/python -e .

# ---

FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash --uid 1000 app

COPY --from=builder --chown=app:app /opt/venv /opt/venv

USER app
WORKDIR /home/app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz').read()" || exit 1

CMD ["python", "-m", "tasks_service"]
