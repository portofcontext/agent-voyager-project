"""The agent's command line (`ping`, `describe`, `run`), which avp-cli and
`avp conformance` call. The agent loads only for `describe` and `run`, so
`ping` stays fast."""

from pydantic import JsonValue

from avp.agent_cli import EventSink, main
from avp.descriptor import AgentDescriptor


def describe() -> AgentDescriptor:
    from avp_pydantic_ai import agent

    return agent.describe()


async def run(received: JsonValue, sink: EventSink) -> None:
    from avp_pydantic_ai import agent

    await agent.run(received, sink)


if __name__ == "__main__":
    raise SystemExit(main(run=run, describe=describe, prog="avp-pydantic-ai"))
