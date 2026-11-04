# Build with this agent directory as the context.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ENV PI_TELEMETRY=0
WORKDIR /avp
COPY . .
RUN npm ci --no-audit --no-fund \
    && npm run build \
    && chmod +x dist/src/main.js
RUN npm link --offline --ignore-scripts --no-audit --no-fund
ENV PATH=/avp/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pi-cli"]
