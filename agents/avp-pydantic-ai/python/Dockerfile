# Build from the repository root to install the SDK and shared data by path.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY avp-sdk/python avp-sdk/python
COPY agents/avp-pydantic-ai/python agents/avp-pydantic-ai/python
RUN uv sync --frozen --no-dev --no-editable --project agents/avp-pydantic-ai/python
ENV PATH=/avp/agents/avp-pydantic-ai/python/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pydantic-ai-cli"]
