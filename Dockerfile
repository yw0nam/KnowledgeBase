FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN uv sync --frozen --no-dev

EXPOSE 8765

CMD ["/app/.venv/bin/kb-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"]
