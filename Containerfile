FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
COPY . /app
WORKDIR /app
RUN uv sync --no-dev --no-editable
CMD ["uv", "run", "jolteon"]
