FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd -m -u 1000 bedrock_agentcore

COPY pyproject.toml uv.lock ./
COPY contracts ./contracts
COPY features ./features
RUN uv sync --frozen --no-dev --package roam-agent

USER bedrock_agentcore

EXPOSE 8080

CMD ["python", "-m", "roam_agent.agentcore_app"]
