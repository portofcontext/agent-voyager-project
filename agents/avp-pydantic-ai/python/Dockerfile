# Built from the repo root, so the agent can install the SDK by path until the
# SDK is on PyPI. From the repo root:
#   avp agent install pd agents/avp-pydantic-ai/python/Dockerfile --context .
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY avp-sdk/python avp-sdk/python
COPY agents/avp-pydantic-ai/python agents/avp-pydantic-ai/python
RUN uv sync --frozen --no-dev --no-editable --project agents/avp-pydantic-ai/python
ENV PATH=/avp/agents/avp-pydantic-ai/python/.venv/bin:$PATH
ENTRYPOINT ["avp-pydantic-ai-cli"]
