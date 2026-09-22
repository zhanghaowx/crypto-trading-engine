FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS engine

WORKDIR /app
COPY . /app
RUN uv sync --frozen --no-default-groups --no-editable

ENTRYPOINT ["uv", "run", "--frozen", "--no-sync", "jolteon"]


FROM engine AS dashboard

RUN uv sync --frozen --no-default-groups --group ui --no-editable

ENTRYPOINT ["uv", "run", "--frozen", "--no-sync", "streamlit", "run", "jolteon/dashboard/main.py"]
CMD ["--server.address=0.0.0.0", "--server.port=8501", "--", "--root", "/data"]
