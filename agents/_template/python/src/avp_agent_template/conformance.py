"""Agent entrypoint (`ping` / `describe` / `run`), via the stock `avp.agent_cli`."""

from avp.agent_cli import main
from avp_agent_template.agent import describe, run

if __name__ == "__main__":
    raise SystemExit(main(run=run, describe=describe, prog="avp-agent-template"))
