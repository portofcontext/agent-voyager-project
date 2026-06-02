# BrowseComp: Exa vs Linkup

Runs two `claude-code` commissions head-to-head on BrowseComp, each wired to a
different web-search backend, and ranks them by accuracy / pass-rate / cost / turns.
Reuses the decrypted dataset from the parent example (`../browse_comp.jsonl`).

## Files

- `browsecomp-search-compare.eval.json` — the eval (both commissions, `llm-judge` scorer).
- `browsecomp-exa.commission.json` — Exa hosted HTTP MCP (`mcp.exa.ai`).
- `browsecomp-linkup.commission.json` — Linkup MCP (the `linkup-mcp-server` binary).
- `web-search-env.json` — opens only the two search endpoints to the sandbox. Exa and
  Linkup crawl server-side, so the agent never needs open-web access.

Both commissions ship with **placeholder keys** (`YOUR_EXA_API_KEY` /
`YOUR_LINKUP_API_KEY`) — insert your own when installing them, never commit a real key.
Each `system_prompt` steers its arm to its own backend, but the agent still has every
builtin tool (the `enabled_builtin_tools` fail-fast validates against the pre-Commission
probe, which can't see MCP tools), so this is soft steering, not a hard block.

## Run

Run from this directory. Do the baseline `## Setup` first (grader extra, agent install,
decrypt), then:

```bash
# Linkup runs as a local binary (no runtime npx fetch, so it works under the sandbox)
npm install -g linkup-mcp-server

# install both commissions with your real keys (do NOT commit these)
sed 's/YOUR_EXA_API_KEY/<exa-key>/'       browsecomp-exa.commission.json    > ~/.avp/commissions/browsecomp-exa.json
sed 's/YOUR_LINKUP_API_KEY/<linkup-key>/' browsecomp-linkup.commission.json > ~/.avp/commissions/browsecomp-linkup.json

export ANTHROPIC_API_KEY=...
uv run avp eval run browsecomp-search-compare.eval.json \
  --max-items 10 --timeout 600 --sandbox on --env web-search-env.json
```

Add `--model claude-sonnet-4-6` to run both arms on a cheaper model than the
commissions' default.
