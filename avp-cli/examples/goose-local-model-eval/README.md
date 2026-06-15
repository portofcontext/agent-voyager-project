# Local models with the goose agent (no ollama)

The goose agent can run an LLM **in-process** with no hosted provider, no API
key, and no external server. It uses goose's `local` provider: a built-in
llama.cpp backend running a quantized GGUF model pulled from Hugging Face.

A commission opts in by naming the `local` provider and a `local/<hf-repo>:<quant>`
model slug. [`goose-local.commission.json`](./goose-local.commission.json):

```json
{
  "model": "local/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M",
  "provider": { "id": "local" }
}
```

## How it runs

The `local` provider does **not** download the model at inference time: it
expects the GGUF already present in goose's model registry. avp provisions that
for you. When a commission routes to `local`, the CLI
([`avp_cli/local_models.py`](../../src/avp_cli/local_models.py)):

1. resolves the GGUF filename for the requested quant from the Hugging Face API,
2. downloads it once into a host cache (`~/.avp/models/`, reused across runs),
3. writes a `registry.json` next to it pointing at the model's in-sandbox path,
4. mounts that cache at `/avp/data/models` — where the agent's `GOOSE_PATH_ROOT`
   looks — so the in-sandbox provider finds it.

The download happens host-side, so the run is deterministic and needs no
in-sandbox network egress. Inference runs on the sandbox's CPU.

## Run it

```bash
# prerequisite: Docker running, and the goose agent built with local-inference
# (agent-goose v0.1.1+).
avp agent install goose

# A) one-off task
avp run "What is 7 multiplied by 6? Respond with only the number." \
  --agent goose --model local/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M

# B) the eval board
cp goose-local.commission.json ~/.avp/commissions/goose-local.json
avp eval run local-model.eval.json
```

The first run downloads ~0.8 GB (the 1B Q4_K_M GGUF) and prints a one-line
notice; later runs reuse the host cache. Cost shows `$0.00` (local inference has
no price). A 1B model is small, so the board may not be all-green; the point of
this example is that the local path runs end-to-end, not the model's accuracy.
Swap in a larger featured model (e.g. `…/Llama-3.2-3B-Instruct-GGUF:Q4_K_M`) for
better answers at the cost of a bigger download and slower CPU inference.
