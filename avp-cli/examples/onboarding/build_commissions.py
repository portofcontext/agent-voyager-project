#!/usr/bin/env python3
"""Generate the per-strategy commissions from the strategy artifacts.

Each onboarding strategy is the SAME commission (same model, same passthrough
prompt) differing only in how AVP knowledge reaches the agent. Rather than paste
each artifact (the 18KB SKILL.md, the llms-full.txt, ...) into JSON by hand and
let them drift, this reads the artifacts in `strategies/` and writes one
`<strategy>/<strategy>.commission.json` per strategy.

    python build_commissions.py            # writes the commission files
    for f in strategies/*/*.commission.json; do cp "$f" ~/.avp/commissions/; done

The dataset (in onboarding.eval.json) supplies each task as the `{input}`; the
commission's prompt is just `{input}`, so every strategy faces the identical task
and the only variable is the onboarding material.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
REPO_ROOT = HERE.parents[2]  # avp-cli/examples/onboarding -> repo root
MODEL = "anthropic/claude-haiku-4-5"

# The skill strategy uses the repo's real SKILL.md (the artifact AVP ships); the
# text strategies inject their artifact as the system prompt.
SKILL_MD = (REPO_ROOT / "SKILL.md").read_text()
LLMS_FULL = (HERE / "strategies/llms-txt/llms-full.txt").read_text()
README_DOCS = (HERE / "strategies/readme-docs/readme-docs.md").read_text()
AGENTS_MD = (HERE / "strategies/agents-md/AGENTS.md").read_text()
EXPLORE = (HERE / "strategies/explore-cli/explore-cli.md").read_text()

MCP_SYSTEM = (
    "You are working with AVP (Agent Voyager Project). You have the avp-knowledge "
    "MCP server connected: call its list_avp_docs, read_avp_doc, and search_avp "
    "tools to look up anything you need about AVP before you answer. Prefer looking "
    "it up over guessing."
)


def base() -> dict:
    """Fields shared by every strategy: same model, prompt passes the task through."""
    return {"schema_version": "0.1", "model": MODEL, "prompt": "{input}"}


# strategy id -> the commission body (merged onto base()). Order matters only for
# readability; the eval references them by id.
STRATEGIES: dict[str, dict] = {
    # Control: no AVP material at all.
    "onboard-cold": {},
    # Skill: the real AVP SKILL.md as an inline skill.
    "onboard-skill": {"skills": [{"id": "avp", "files": {"SKILL.md": SKILL_MD}}]},
    # Text strategies: the artifact injected as the system prompt.
    "onboard-llms-txt": {"system_prompt": LLMS_FULL},
    "onboard-readme-docs": {"system_prompt": README_DOCS},
    "onboard-agents-md": {"system_prompt": AGENTS_MD},
    # Needs in-sandbox tooling (excluded from the first run; see README):
    "onboard-explore-cli": {
        "system_prompt": EXPLORE,
        "enabled_builtin_tools": ["shell", "bash", "write", "edit"],
    },
    "onboard-mcp": {
        "system_prompt": MCP_SYSTEM,
        # The server is fetched + run by uvx from this repo's subdirectory (GitHub
        # egress is in the sandbox's default allowlist). It runs once the example
        # is on the default branch; for a local server use `uvx --from
        # strategies/mcp avp-knowledge-mcp`, or publish it and use `uvx avp-knowledge-mcp`.
        "mcp_servers": [
            {
                "type": "stdio",
                "id": "avp-knowledge",
                "command": [
                    "uvx",
                    "--from",
                    "git+https://github.com/portofcontext/agent-voyager-project.git#subdirectory=avp-cli/examples/onboarding/strategies/mcp",
                    "avp-knowledge-mcp",
                ],
            }
        ],
    },
}


def main() -> None:
    for strategy, body in STRATEGIES.items():
        commission = {**base(), "run_id": strategy, **body}
        out = (
            HERE / "strategies" / strategy.removeprefix("onboard-") / f"{strategy}.commission.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(commission, indent=2) + "\n")
        print(f"wrote {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
