"""The agent command line; load the native graph only for describe or run."""

from pydantic import JsonValue

from avp.agent_cli import EventSink
from avp.agent_cli import main as agent_main


def describe():
    from avp_deep_agents.descriptor import describe as describe_agent

    return describe_agent()


async def run(received: JsonValue, sink: EventSink) -> None:
    from avp_deep_agents.agent import run as run_agent

    await run_agent(received, sink)


def main(argv: list[str] | None = None) -> int:
    return agent_main(run=run, describe=describe, prog="avp-deep-agents-cli", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
