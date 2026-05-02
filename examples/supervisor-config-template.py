"""Supervisor Config — minimal template.

Use this when you're the supervisor side: you're declaring an agent's complete
environment up front. The agent runs inside what you declared; you observe the
trajectory; you don't reach in mid-run.

This template builds a Config that exercises every supervisor primitive:
boundary, tools (both local and RPC), re_observation (shell + supervisor RPC),
verifiers (all three on_failure modes), output_schema, skills.

To run:
    pip install -e python/aep
    python examples/supervisor-config-template.py
"""

from __future__ import annotations

from aep import Config


def build_config(*, run_id: str = "demo-supervisor-config") -> Config:
    """A worked example: a code-refactoring agent operating inside a Rust repo.

    Read alongside spec/v0.1/SPEC.md sections §7 (verifiers), §8 (tools),
    §9 (re-observation), §10.2 (boundary semantics)."""

    return Config(
        schema_version="0.1",
        run_id=run_id,
        # ── Tools ──────────────────────────────────────────────────────────
        # These are tools whose IMPLEMENTATION is a supervisor-stood-up RPC
        # service. The runner emits tool_exec_request when the model calls
        # them; the supervisor's service replies with tool_exec_resolved.
        # Tools the runner has built in locally (bash, file IO) are NOT
        # declared here.
        tools=[
            {
                "name": "lookup_user",
                "description": "Look up a user by email in the corporate directory.",
                "input_schema": {
                    "type": "object",
                    "required": ["email"],
                    "properties": {"email": {"type": "string", "format": "email"}},
                    "additionalProperties": False,
                },
                "timeout_ms": 15000,
            },
        ],
        # ── Re-observation ─────────────────────────────────────────────────
        # State refresh sources the agent runs before turns to combat context
        # rot. Source can be {shell: ...} (runner runs locally) or
        # {supervisor: true} (runner makes an RPC).
        re_observation=[
            {
                "name": "git_state",
                "source": {"shell": "git status --porcelain && git diff --stat"},
                "trigger": "before_each_turn",
                "max_tokens": 500,
            },
            {
                "name": "session_context",
                "source": {"supervisor": True},  # RPC: runner emits re_observation_request
                "trigger": "every_n_turns",
                "every_n": 3,
                "max_tokens": 1000,
                "timeout_ms": 5000,
            },
        ],
        # ── Verifiers — the deterministic-rule primitive ───────────────────
        # Three on_failure modes; pick the one that matches the rule.
        verifiers=[
            {
                "name": "tests-pass",
                "trigger": "after_each_turn",
                "source": {"shell": "cargo test --quiet"},
                "on_failure": "halt",  # DDD-invariant pattern: agent_stopped reason='verifier_failed'
            },
            {
                "name": "no-secrets-leaked",
                "trigger": "on_tool:write_file",
                "source": {"shell": "scripts/scan_secrets.sh"},
                "on_failure": "inject_correction",  # Self-correcting agent pattern
                "correction_message": (
                    "The last write contained a secret. Revert it and try again."
                ),
            },
            {
                "name": "lint-clean",
                "trigger": "at_end",
                "source": {"shell": "cargo clippy --quiet"},
                "on_failure": "continue",  # Monitor-only — record the fact, don't halt
            },
        ],
        # ── Boundary — strict-greater algorithm ────────────────────────────
        # max_steps: N → run completes EXACTLY N turns (projection check).
        # max_cost_usd / max_tokens: run MAY overshoot by one final turn
        # (post-event check; cost can't be projected pre-call).
        boundary={
            "max_cost_usd": 2.00,
            "max_steps": 30,
            "max_tokens": 150000,
        },
        # ── What the agent produces ────────────────────────────────────────
        output_schema={
            "type": "object",
            "required": ["summary", "files_changed"],
            "properties": {
                "summary": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
            },
        },
        # ── What the agent runs ────────────────────────────────────────────
        prompt="Refactor the auth module to use JWT.",
        system_prompt="You are a senior Rust developer.",
        model="claude-sonnet-4-6",
        skills=[
            {"name": "style-guide", "source": "./skills/style-guide"},
        ],
        # ── Metadata for downstream filtering ──────────────────────────────
        thread_id="session-xyz",
        tags=["auth", "refactor", "rust"],
        meta={"environment": "dev", "triggered_by": "ci"},
    )


def main() -> None:
    config = build_config()
    print(config.model_dump_json(indent=2, exclude_none=True))


if __name__ == "__main__":
    main()
