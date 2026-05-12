"""`avp-claude-agent-conformance` console-script entry.

All CLI behavior comes from `avp.conformance.sdk_harness.make_cli`; the
SDK-specific runner lives in `avp_claude_agent.conformance`. Keeping
this file in place (instead of pointing `pyproject.toml` directly at
`avp_claude_agent.conformance:main`) preserves the historical script
path for tab-completion / shell scripts.
"""

from __future__ import annotations

from avp_claude_agent.conformance import main

if __name__ == "__main__":
    raise SystemExit(main())
