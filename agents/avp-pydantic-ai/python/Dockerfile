# Build with this agent directory as the context.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY . .
RUN uv sync --frozen --no-dev --no-editable
ENV PATH=/avp/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pydantic-ai-cli"]
