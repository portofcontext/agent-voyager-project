# Set up AVP

Requires macOS or Linux, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and a running [Docker daemon](https://docs.docker.com/get-started/get-docker/).

Install the CLI and agents if needed:

```bash
uv tool install avp-cli
avp agent install --all
```

If the user wants specific agents, install each with `avp agent install <name>`
(for example, `codex`, `claude-code`, or `pi`).

Run `avp env secret list` to see stored credential names. Choose an agent and
model for a provider the user has configured. For missing keys, have the user
run `avp env secret create <name>` locally and enter the key at the prompt.
Use names such as `openai`, `anthropic`, or `google`; never ask for secrets in chat.
See the [authentication guide](https://github.com/portofcontext/agent-voyager-project/blob/main/avp-cli/README.md#model-authentication)
for key creation links and Commission references.

For the Claude Code sample, the user stores an Anthropic API key once:

```bash
avp env secret create anthropic
```

Run the bundled sample with Claude Code, or adapt its agent and model to the
user's configured provider. Attach the stored credential to each Commission
before running. This example makes paid model calls:

```bash
avp init capitals --agent claude-code
for id in capitals-baseline capitals-few-shot; do
  avp cm create "$id" --from "$id" --force --provider-id anthropic --credential anthropic
done
avp eval run capitals.eval.json
```

Without Docker, add `--runtime local` to the run command; this adds no OS isolation.

For the user's task, explore `avp --help` and relevant subcommand help. Validate
Commissions before running them. Inspect saved trajectories and scores, fix
failures, and report results with reproducible commands.
