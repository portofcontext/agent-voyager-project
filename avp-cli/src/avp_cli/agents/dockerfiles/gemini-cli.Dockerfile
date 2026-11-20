# Build with the repository root as the context.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ripgrep && rm -rf /var/lib/apt/lists/*
WORKDIR /repo
COPY avp-sdk/typescript avp-sdk/typescript
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1 spec/v0.1
COPY agents/avp-gemini-cli/typescript agents/avp-gemini-cli/typescript
WORKDIR /repo/avp-sdk/typescript
RUN npm ci --no-audit --no-fund && npm run build
WORKDIR /repo/agents/avp-gemini-cli/typescript
RUN npm ci --no-audit --no-fund \
    && npm run build \
    && chmod +x dist/src/main.js
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/repo/agents/avp-gemini-cli/typescript/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-gemini-cli-cli"]
