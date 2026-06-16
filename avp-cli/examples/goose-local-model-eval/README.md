# Eval goose on a local model over a Hugging Face dataset

This evals the **goose** agent on [GSM8K](https://huggingface.co/datasets/openai/gsm8k)
(grade-school math) while goose runs against a **local model server on your own
machine**: no hosted provider, no API keys, fully deterministic scoring, `$0.00`
per run. goose runs sandboxed and talks to an OpenAI-compatible server (llama.cpp,
Ollama, LM Studio, ...) on your host, so the model uses your real GPU and stays
loaded warm across the whole eval.

In our run, `Qwen2.5-7B-Instruct` (Q4) scored **9/10** with step-by-step
reasoning, at `$0.00`.

The eval is one file. The dataset is pulled straight from the Hub by id, no
download script or CSV. The agent returns a structured `{"answer": N}` (a
Commission `output_schema`), and `structural-match` compares it to the gold
integer, so scoring is exact and needs no judge:

```json
{
  "name": "gsm8k-local",
  "agents": ["goose"],
  "dataset": {
    "source": "huggingface",
    "id": "openai/gsm8k", "config": "main", "split": "test[:10]",
    "input": "{question}", "expected_field": "answer",
    "expected_pattern": "####\\s*([-0-9,]+)", "expected_key": "answer"
  },
  "scorer": { "name": "structural-match" },
  "commissions": ["gsm8k-local"]
}
```

GSM8K's `answer` field is the full worked solution ending in `#### 18`;
`expected_pattern` extracts the gold integer and `expected_key` wraps it as
`{"answer": 18}`, the shape `structural-match` scores the agent's structured
output against. The model may still reason step by step; only its final
structured answer is scored.

## Run it

Prerequisites: Docker running and the goose agent (`avp agent install goose`).
No model API key, no judge key: the model is local and scoring is deterministic.

**1. Serve a model on your host.** With llama.cpp (`brew install llama.cpp`):

```bash
llama-server -m Qwen2.5-7B-Instruct-Q4_K_M.gguf --port 8080 -ngl 999 -c 16384 -fa on
```

Any OpenAI-compatible server works (`ollama serve`, LM Studio, vLLM); point the
commission's `provider.base_url` at it.

**2. Run the eval.** The commission
([`gsm8k-local.commission.json`](./gsm8k-local.commission.json)) routes goose at
the host server via `host.docker.internal`, declares the `{"answer": integer}`
`output_schema`, and turns goose's tools off (math needs none, which keeps the
prompt small and fast):

```bash
export OPENAI_API_KEY=sk-local        # any non-empty value; the local server ignores it

cp gsm8k-local.commission.json ~/.avp/commissions/gsm8k-local.json
avp eval run gsm8k.eval.json --env env.json
```

`avp eval view` opens the scored board.

## Run a different / bigger brain

Serve a different GGUF in step 1 (the swap is the model file), then update the
model name in `gsm8k-local.commission.json`:

```diff
-  "model": "openai/qwen2.5-7b",
+  "model": "openai/llama-3.1-70b",
```

The local server picks the model; the `model` string is just a label here. A
bigger model needs more VRAM but the eval config is unchanged.

## Swap the dataset

Any Hub dataset works: change `id`, `config`, `split`, and the `{input}` /
`expected_field` mappings. The `test[:10]` slice keeps the demo cheap; drop it
to run the full split.
