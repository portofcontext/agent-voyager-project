"""The agent command line; load the model runtime only for run."""

from pydantic import JsonValue

from avp.agent_cli import EventSink
from avp.agent_cli import main as agent_main
from avp_openai_agents.descriptor import describe


async def run(received: JsonValue, sink: EventSink) -> None:
    from avp_openai_agents.agent import run as run_agent

    await run_agent(received, sink)


def main(argv: list[str] | None = None) -> int:
    return agent_main(run=run, describe=describe, prog="avp-openai-agents-cli", argv=argv)


if __name__ == "__main__":
    raise SystemExit(main())
