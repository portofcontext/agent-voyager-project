# Build from the repository root to install the SDK and shared data by path.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ENV PI_TELEMETRY=0
WORKDIR /avp
COPY avp-sdk/data avp-sdk/data
COPY spec/v0.1/*.schema.json spec/v0.1/
COPY avp-sdk/typescript avp-sdk/typescript
COPY agents/avp-pi/typescript agents/avp-pi/typescript
RUN npm --prefix avp-sdk/typescript ci --ignore-scripts --no-audit --no-fund \
    && npm --prefix avp-sdk/typescript run build \
    && npm --prefix agents/avp-pi/typescript ci --no-audit --no-fund \
    && npm --prefix agents/avp-pi/typescript run build \
    && chmod +x agents/avp-pi/typescript/dist/src/main.js
WORKDIR /avp/agents/avp-pi/typescript
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/avp/agents/avp-pi/typescript/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pi-cli"]
