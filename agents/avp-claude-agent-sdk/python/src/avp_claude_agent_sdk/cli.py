"""The agent command line, with the native SDK loaded only for run."""

from pydantic import JsonValue

from avp.agent_cli import TrajectorySink
from avp.agent_cli import main as agent_main
from avp_claude_agent_sdk.descriptor import describe


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    from avp_claude_agent_sdk.agent import run as run_agent

    await run_agent(received, sink)


def main(argv: list[str] | None = None) -> int:
    return agent_main(run=run, describe=describe, prog="avp-claude-agent-sdk-cli", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
