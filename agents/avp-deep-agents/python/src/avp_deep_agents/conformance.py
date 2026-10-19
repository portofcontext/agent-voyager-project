"""Agent entrypoint (`ping` / `describe` / `run`), via the stock `avp.agent_cli`."""

from avp.agent_cli import main
from avp_deep_agents.agent import describe, run

if __name__ == "__main__":
    raise SystemExit(main(run=run, describe=describe, prog="avp-deep-agents"))
