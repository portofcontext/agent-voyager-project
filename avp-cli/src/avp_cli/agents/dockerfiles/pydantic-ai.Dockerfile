# Build with the repository root as the context.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /repo
COPY avp-sdk/python avp-sdk/python
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1 spec/v0.1
COPY agents/avp-pydantic-ai/python agents/avp-pydantic-ai/python
WORKDIR /repo/agents/avp-pydantic-ai/python
RUN uv sync --frozen --no-dev --no-editable
ENV PATH=/repo/agents/avp-pydantic-ai/python/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pydantic-ai-cli"]
