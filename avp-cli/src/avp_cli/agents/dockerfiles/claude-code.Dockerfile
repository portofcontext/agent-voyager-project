# Build with this agent directory as the context.
FROM node:24-slim AS claude
RUN npm install --global @anthropic-ai/claude-code@2.1.303
FROM python:3.14-slim
COPY --from=claude /usr/local/bin/node /usr/local/bin/node
COPY --from=claude /usr/local/bin/claude /usr/local/bin/claude
COPY --from=claude /usr/local/lib/node_modules/@anthropic-ai /usr/local/lib/node_modules/@anthropic-ai
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy IS_SANDBOX=1 CLAUDE_CONFIG_DIR=/tmp/avp-claude
WORKDIR /avp
COPY . .
RUN uv sync --frozen --no-dev --no-editable
ENV PATH=/avp/.venv/bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-claude-agent-sdk-cli"]
