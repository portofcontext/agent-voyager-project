# Build from the repository root so uv can install the SDK and shared data by path.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY avp-sdk/python avp-sdk/python
COPY agents/avp-codex/python agents/avp-codex/python
RUN uv sync --frozen --no-dev --no-editable --project agents/avp-codex/python
ENV PATH=/avp/agents/avp-codex/python/.venv/bin:$PATH CODEX_HOME=/tmp/avp-codex
# OpenSandbox supplies confinement. Avoid nesting Codex's OS sandbox inside it.
RUN mkdir -p "$CODEX_HOME" && printf 'sandbox_mode = "danger-full-access"\n' > "$CODEX_HOME/config.toml"
WORKDIR /workspace
ENTRYPOINT ["avp-codex-cli"]
