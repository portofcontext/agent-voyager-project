"""The agent's command line (`ping`, `describe`, `run`), installed as
`avp-pydantic-ai-cli`, which avp-cli and `avp conformance` call. Pydantic AI
loads only for `run`, so `ping` and `describe` stay fast."""

from pydantic import JsonValue

from avp.agent_cli import EventSink
from avp.agent_cli import main as agent_cli_main
from avp_pydantic_ai.descriptor import describe


async def run(received: JsonValue, sink: EventSink) -> None:
    from avp_pydantic_ai import agent

    await agent.run(received, sink)


def main() -> None:
    raise SystemExit(agent_cli_main(run=run, describe=describe, prog="avp-pydantic-ai-cli"))


if __name__ == "__main__":
    main()
