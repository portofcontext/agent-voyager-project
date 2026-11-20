# Build with the repository root as the context.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /repo
COPY avp-sdk/python avp-sdk/python
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1 spec/v0.1
COPY agents/avp-deep-agents/python agents/avp-deep-agents/python
WORKDIR /repo/agents/avp-deep-agents/python
RUN uv sync --frozen --no-dev --no-editable
ENV PATH=/repo/agents/avp-deep-agents/python/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-deep-agents-cli"]
