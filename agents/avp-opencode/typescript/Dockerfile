# Build from the repository root; native binaries and tools install at build time.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ripgrep && rm -rf /var/lib/apt/lists/*
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1/*.schema.json spec/v0.1/
COPY avp-sdk/typescript avp-sdk/typescript
COPY agents/avp-opencode/typescript agents/avp-opencode/typescript
RUN npm --prefix avp-sdk/typescript ci --ignore-scripts --no-audit --no-fund \
    && npm --prefix avp-sdk/typescript run build \
    && npm --prefix agents/avp-opencode/typescript ci --ignore-scripts --no-audit --no-fund \
    && npm --prefix agents/avp-opencode/typescript run build \
    && chmod +x agents/avp-opencode/typescript/dist/src/main.js
WORKDIR /avp/agents/avp-opencode/typescript
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/avp/agents/avp-opencode/typescript/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-opencode-cli"]
