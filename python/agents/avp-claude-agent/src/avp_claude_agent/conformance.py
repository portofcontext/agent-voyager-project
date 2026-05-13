"""`avp-claude-agent-conformance` console-script entry.

Drives `ClaudeAgentTranslator.run()` against the real Claude Agent SDK.
The runner is assumed to have:

  - `ANTHROPIC_API_KEY` in env,
  - the `claude` CLI on `PATH`,

i.e. CASDK's normal runtime requirements. There's no scripted SDK
substitute and no fakery — what conformance sees on the wire is what
production sees on the wire. Cases marked `scripted_only` need a
deterministic model and are skipped here; they're only run against the
reference agent via `avp-conformance`.

All the wire-up (case loading, commission/descriptor/resolver building,
expectation evaluation, CLI flags) lives in `avp.conformance.sdk_harness`.
"""

from __future__ import annotations

from avp.conformance.sdk_harness import make_translator_cli
from avp_claude_agent.translator import ClaudeAgentTranslator

main = make_translator_cli(
    translator_cls=ClaudeAgentTranslator,
    prog="avp-claude-agent-conformance",
    description="Run v0.1 conformance cases against ClaudeAgentTranslator.",
    skip_flags={
        "scripted_only": "scripted_only — requires a deterministic-model harness",
    },
)


if __name__ == "__main__":
    raise SystemExit(main())
