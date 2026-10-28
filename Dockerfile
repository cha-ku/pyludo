FROM ghcr.io/astral-sh/uv:0.13.0-python3.14-trixie-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy FORWARDED_ALLOW_IPS=*

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --system pyludo
USER pyludo

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "pyludo.server:app", "--host", "0.0.0.0", "--port", "8000"]
