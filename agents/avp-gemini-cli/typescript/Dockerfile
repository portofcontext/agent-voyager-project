# Build from the repository root; install all native requirements before launch.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates ripgrep && rm -rf /var/lib/apt/lists/*
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1/*.schema.json spec/v0.1/
COPY avp-sdk/typescript avp-sdk/typescript
COPY agents/avp-gemini-cli/typescript agents/avp-gemini-cli/typescript
RUN npm --prefix avp-sdk/typescript ci --ignore-scripts --no-audit --no-fund \
    && npm --prefix avp-sdk/typescript run build \
    && npm --prefix agents/avp-gemini-cli/typescript ci --no-audit --no-fund \
    && npm --prefix agents/avp-gemini-cli/typescript run build \
    && chmod +x agents/avp-gemini-cli/typescript/dist/src/main.js
WORKDIR /avp/agents/avp-gemini-cli/typescript
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/avp/agents/avp-gemini-cli/typescript/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-gemini-cli-cli"]
