# Build with this agent directory as the context.
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /avp
COPY . .
RUN uv sync --frozen --no-dev --no-editable
ENV PATH=/avp/.venv/bin:$PATH CODEX_HOME=/tmp/avp-codex
# OpenSandbox supplies confinement. Avoid nesting Codex's OS sandbox inside it.
RUN mkdir -p "$CODEX_HOME" && printf 'sandbox_mode = "danger-full-access"\n' > "$CODEX_HOME/config.toml"
WORKDIR /workspace
ENTRYPOINT ["avp-codex-cli"]
