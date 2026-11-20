# Installs released packages; no repository build context is needed.
FROM node:24-slim AS claude
RUN npm install --global @anthropic-ai/claude-code@2.1.303
FROM python:3.14-slim
COPY --from=claude /usr/local/bin/node /usr/local/bin/node
COPY --from=claude /usr/local/bin/claude /usr/local/bin/claude
COPY --from=claude /usr/local/lib/node_modules/@anthropic-ai /usr/local/lib/node_modules/@anthropic-ai
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy IS_SANDBOX=1 CLAUDE_CONFIG_DIR=/tmp/avp-claude
RUN uv pip install --system \
    https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-python-v0.1.0b3/agent_voyager_project-0.1.0b3-py3-none-any.whl \
    https://github.com/portofcontext/agent-voyager-project/releases/download/agent-claude-code-v0.2.5/avp_claude_agent_sdk-0.2.5-py3-none-any.whl
WORKDIR /workspace
ENTRYPOINT ["avp-claude-agent-sdk-cli"]
