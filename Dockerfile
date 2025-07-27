FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src"

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV MCP_SSE_PORT=8000
ENV MCP_STREAMABLE_HTTP_PORT=8080

EXPOSE ${MCP_SSE_PORT} ${MCP_STREAMABLE_HTTP_PORT}

WORKDIR /app

ENTRYPOINT ["uv", "run", "src/main.py"]
