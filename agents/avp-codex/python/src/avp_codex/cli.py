"""The SDK's agent command line, installed as `avp-codex-cli`."""

from pydantic import JsonValue

from avp.agent_cli import TrajectorySink
from avp.agent_cli import main as agent_cli_main
from avp_codex.descriptor import describe


async def run(received: JsonValue, sink: TrajectorySink) -> None:
    from avp_codex import agent

    await agent.run(received, sink)


def main() -> None:
    raise SystemExit(agent_cli_main(run=run, describe=describe, prog="avp-codex-cli"))


if __name__ == "__main__":
    main()
