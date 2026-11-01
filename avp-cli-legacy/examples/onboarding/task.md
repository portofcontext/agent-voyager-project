Set up AVP from scratch and use it to compare two Commission variants on a dataset.
AVP's repository is https://github.com/portofcontext/agent-voyager-project.

The workspace contains inputs/CLI_WHEEL, an unpublished CLI
build under test. Install that wheel, not the public CLI release. Python, pip,
uv, network access for package installs, and provider credentials are available.
Do not print credentials. Keep the inherited provider endpoint settings.

This trial already runs inside a container. Use `--runtime local` for child AVP
runs: no nested Docker daemon is available. Use MODEL_SLUG for all child models.
Set AVP_HOME to an absolute path at workspace/child-home so the evidence survives.
Do not reuse the outer supervisor's files or modify inputs/.

Produce these artifacts in the workspace:

1. Install and register the released pydantic-ai adapter with AVP.
2. Create two Commissions, each with a different instruction
   strategy, `{input}` in its prompt, and an output schema requiring an integer
   `answer` in a JSON object. Validate both with the CLI.
3. Create comparison.eval.json. Use the questions and expected answers from
   inputs/cases.jsonl as a file dataset. You may map its fields or create a
   converted copy without modifying the original. Use
   structural-match with threshold 1.0, and compare both Commissions on all three
   cases with pydantic-ai. Do not substitute different cases or use a scripted agent.
4. Run the evaluation, saving the machine-readable board as child-board.json and
   the run artifacts beneath child-output/. Keep the run manifest and all six
   trajectories. Inspect errors and fix your configuration if needed.
5. Resume the completed run using AVP's resume option. Save the resumed board as
   resumed-board.json. Confirm it reuses the completed trajectories.
6. Write report.md with the two strategies, scores, total reported model cost,
   and which strategy you would choose based on this small dataset. Include
   commands needed to reproduce it. Be candid about errors or inconclusive results.

Do the work, not just describe the commands. Return DONE only after verifying it.
