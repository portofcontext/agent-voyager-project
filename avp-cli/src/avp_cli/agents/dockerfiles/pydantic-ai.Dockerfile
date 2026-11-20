# Installs released packages; no repository build context is needed.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
RUN uv pip install --system \
    https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-python-v0.1.0b3/agent_voyager_project-0.1.0b3-py3-none-any.whl \
    https://github.com/portofcontext/agent-voyager-project/releases/download/agent-pydantic-ai-v0.0.6/avp_pydantic_ai-0.0.6-py3-none-any.whl
WORKDIR /workspace
ENTRYPOINT ["avp-pydantic-ai-cli"]
