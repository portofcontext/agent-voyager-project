# AVP onboarding AVP

Can a coding agent complete an advanced AVP evaluation without a skill? This
experiment gives agents an installation task, a CLI wheel, and configured
credentials, then varies the additional material on their Commissions.

## Task and comparisons

The [task](task.md) starts with installing an unpublished CLI wheel and an agent.
It requires a file dataset, two Commission variants, structured output, six real
child runs, trajectory inspection, a resumed evaluation, and an evidence report.

| Arm | Additional Commission input |
|---|---|
| `repo` | Repository URL only, in the common task |
| `prompt` | The short public [PROMPT.md](PROMPT.md) as instructions |
| `cli-docs` | The current CLI guide as instructions |
| `skill` | The complete packaged AVP skill, including its offline references |
| `skill-invoked` | The same skill plus an explicit instruction to use it |

The comparison uses Codex, Claude Code, and Pi. Each gets the same task and
uses its native tools. Compare onboarding inputs within each agent; differences
between agents also include their models and runtime behavior. Skill loading is
part of what is measured.
The default models are GPT-5.5 for Codex and Claude Sonnet 4.6 for Claude Code
and Pi.

Each trial is a separate one-cell `avp eval run`, with a fresh container, home,
and workspace. The agent installs and invokes the CLI itself. Child runs use
`--runtime local` inside the outer container, without a nested Docker daemon.

## Observed local results

On October 22, 2026, all five inputs completed the task on all three agents:
15 successful trials. One fresh short-prompt repeat per agent also passed.
Each trial installed AVP, ran six real child cases, resumed the evaluation,
and saved artifacts that passed the same final grader and trajectory review.

Reported model cost in USD, including the outer agent and its child runs:

| Agent | Repository | Short prompt | CLI docs | Skill | Skill explicitly invoked |
|---|---:|---:|---:|---:|---:|
| Codex | $1.02 | $1.12 | $1.03 | $2.36 | $2.22 |
| Claude Code | $0.50 | $0.84 | $0.81 | $0.55 | $0.67 |
| Pi | $0.47 | $0.44 | $0.42 | $0.40 | $0.38 |

Each table cell is one trial. The additional short-prompt repeats cost $0.88
for Codex, $0.81 for Claude Code, and $0.34 for Pi. Total reported cost for
these 18 trials was $15.25, excluding earlier calibration and conformance runs.
Costs include caching and are observations, not estimates of future billing.

The tested short prompt preceded the installation instructions now in
`PROMPT.md` and was injected into the Commission, not fetched from a public link.
Saved Commissions retain the exact evaluated text. These trials did not test
public-package discovery, credential setup, or the README onboarding flow.

All inputs completed the task; this sample does not establish a winner. The
README provides installation and credential instructions, followed by a prompt
for the agent. The skill remains optional.

This was one prescribed task with an unpublished CLI wheel, local Codex and
Claude adapter fixes, and a released Pi adapter. Startup failures found during
calibration were repaired before this comparison. Artifact grading accepts
equivalent paths and copied run directories, verifies the saved trajectories,
and ignores the manifest timestamp rewritten by resume. Raw trial records and
the original grades remain in ignored local run directories. This small study
does not establish reliability across developer tasks or measure native skill
installation into an interactive session.

## Run locally

From the repository root, with uv, Docker, and provider credentials available:

```bash
uv build --package avp-cli --wheel
make build-agents AGENTS="codex claude-code"
uv run avp agent install codex --as codex-onboarding --from dist/agents/codex
uv run avp agent install claude-code --as claude-onboarding --from dist/agents/claude-code
uv run avp agent install pi
uv run python avp-cli/examples/onboarding/build_commissions.py \
  --wheel dist/avp_cli-0.5.0-py3-none-any.whl \
  --out dist/onboarding --repetitions 1 \
  --agent codex=codex-onboarding --agent claude-code=claude-onboarding
uv run python avp-cli/examples/onboarding/run.py dist/onboarding \
  --agents claude-code --max-reported-cost 10
```

Preparation makes no model calls. Execution does. Set provider API keys in the
calling environment; selected credentials and endpoints follow the normal AVP
launcher policy. Use `DOCKER_HOST` if your Docker installation needs it.
Omit `--agents` to run all three agents; use `--strategies` for a comma-separated subset.
Preparation accepts repeated `--model AGENT=ORIGIN/MODEL` overrides. Keep each
agent's model fixed across its comparison arms.
Use `--agent codex=codex-local` or another installed alias to compare local
adapter builds. Build and install those through the normal
[local build workflow](../../README.md#agents-install--local-dev); their artifact hashes
are recorded in each run manifest. Local fixes require local builds until they
are released.
The cost limit is checked between trials using reported trajectory costs. It is
not a hard billing cap and may undercount interrupted child runs.

Generated Commissions, eval configs, wheel/material hashes, seeded order, logs,
and results stay in the batch directory. The ordinary AVP run directories retain
outer trajectories, exact Commission snapshots, child artifacts, and workspaces.
Re-running the runner skips recorded trials; a new batch is required to retry a
trial with changed inputs.

## Scoring

The outer exact-match score records whether the agent said `DONE`. It does **not**
determine onboarding success. [verify.py](verify.py) separately checks the saved
configuration, released adapter provenance, six successful child trajectories,
correct structured answers, resume results, unchanged fixtures, and report.
The grader loads the dataset through AVP and checks the supplied questions and
answers, allowing equivalent field mappings and Commission names. It also
re-scores saved traces through the resume path without making model calls.
Results distinguish task compliance from a completed evaluation and record
wall time, turns, tokens, and reported model cost. Inspect the trajectories
alongside the artifact checks when comparing strategies.

These trials measure Commission inputs through AVP adapters. Codex embeds skill
files in developer instructions; Claude Code and Pi load materialized skill
files. This does not directly measure installing a skill into an existing
interactive coding session. Treat launch failures separately from onboarding
failures, and repeat promising comparisons before changing distribution.
