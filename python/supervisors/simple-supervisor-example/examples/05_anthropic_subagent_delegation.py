"""Example 05 — Subagent delegation (Phase 5 punch-list).

The original example demonstrated in-process subagent dispatch via the
deleted `AnthropicSubagentDriver`. That mechanism is gone in v0.1's
refs-only Commission model — managed subagents now spawn through the AVP
resolver protocol (`avp.spawn_subagent`), which the avp-anthropic CLI
doesn't yet wire (Phase 5 follow-up).

Re-running this example once the resolver is implemented in the CLI will
produce a cleaner trajectory: parent's `subagent_invoked` carries
`avp.subagent.run_id` referencing the child's separate trajectory, the
child runs as its own commission, and the supervisor correlates the two
streams via that id.
"""

from __future__ import annotations


def main() -> int:
    print(
        "example 05: subagent delegation is on the Phase 5 punch-list "
        "pending the avp-anthropic CLI's resolver protocol implementation. "
        "See SPEC.md §6 for the resolver protocol and §9.5 for the new "
        "subagent lifecycle."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
