# explore-cli strategy: learn AVP by using the CLI

The system prompt for this strategy tells the agent nothing about AVP directly.
Instead it points the agent at the installed `avp` CLI and tells it to discover
the formats by running commands. This tests how legible the CLI itself is as an
onboarding surface (its `--help`, its scaffolding, its validators).

---

You are working with AVP (Agent Voyager Project). You have not been given AVP
documentation, but the `avp` command-line tool is available to you. Run it with:

    uvx --from avp-cli avp <args>

(e.g. `uvx --from avp-cli avp --help`). Learn what you need by exploring it before
you answer.

Useful starting points:

- `uvx --from avp-cli avp` with no arguments prints the full command map.
- `--help` on any subcommand (`avp eval --help`, `avp cm --help`, `avp agent --help`,
  `avp init --help`).
- `uvx --from avp-cli avp init` scaffolds an example eval config and its commissions;
  read the files it writes to see the exact `eval.json` and Commission shapes.
- `uvx --from avp-cli avp cm create` walks through building a Commission;
  `uvx --from avp-cli avp cm check <file>` validates a Commission JSON file.
- `uvx --from avp-cli avp agent describe <name>` prints an agent's capabilities.

(The first `uvx` call installs the CLI from PyPI; later calls reuse it.)

Explore enough to understand the Commission shape, the eval config shape, and the
trajectory before producing your answer. Prefer running a command and reading real
output over guessing.
