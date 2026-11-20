# Installs released packages; no repository build context is needed.
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ENV PI_TELEMETRY=0
WORKDIR /opt/avp
RUN npm install --omit=dev --no-audit --no-fund \
    https://github.com/portofcontext/agent-voyager-project/releases/download/sdk-typescript-v0.1.0-beta.3/agent-voyager-project-sdk-0.1.0-beta.3.tgz \
    https://github.com/portofcontext/agent-voyager-project/releases/download/agent-pi-v0.1.4/avp-pi-0.1.4.tgz
ENV PATH=/opt/avp/node_modules/.bin:$PATH
WORKDIR /workspace
ENTRYPOINT ["avp-pi-cli"]
