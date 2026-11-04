# Build from the repository root to install the SDK and shared data by path.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY avp-sdk/python avp-sdk/python
COPY agents/avp-deep-agents/python agents/avp-deep-agents/python
RUN uv sync --frozen --no-dev --no-editable --project agents/avp-deep-agents/python
ENV PATH=/avp/agents/avp-deep-agents/python/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-deep-agents-cli"]
