# Build with the repository root as the context.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ripgrep && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY avp-sdk/typescript avp-sdk/typescript
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1 spec/v0.1
COPY agents/avp-opencode/typescript agents/avp-opencode/typescript
WORKDIR /repo/avp-sdk/typescript
RUN npm ci --no-audit --no-fund && npm run build
WORKDIR /repo/agents/avp-opencode/typescript
RUN npm ci --ignore-scripts --no-audit --no-fund \
    && npm run build \
    && chmod +x dist/src/main.js
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/repo/agents/avp-opencode/typescript/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-opencode-cli"]
