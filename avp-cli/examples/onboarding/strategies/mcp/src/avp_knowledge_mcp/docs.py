"""The AVP knowledge base the server serves. Kept as plain strings so the server
runs offline (no repo or network access needed inside a sandbox)."""

from __future__ import annotations

DOCS: dict[str, str] = {
    "overview": (
        "AVP (Agent Voyager Project) is an open standard for the agent-execution "
        "case. A supervisor sends an agent a JSON Commission (what to do, which "
        "model, what resources); the agent runs and streams back a Trajectory of "
        "CloudEvents the supervisor observes. There is no supervisor-to-agent push "
        "channel: once the Commission is sent, the supervisor only observes. Four "
        "specs compose independently: Commission, Trajectory, Agent Descriptor, and "
        "the optional Resolver API. AVP specializes existing standards: CloudEvents "
        "1.0 envelope, OpenTelemetry span ids, JSON-RPC 2.0 for refs, MCP-shaped "
        "tools, Agent Skills SKILL.md."
    ),
    "commission": (
        "A Commission is the run config the supervisor sends at startup. Required: "
        "schema_version ('0.1'), run_id, and model as a canonical 'origin/model' "
        "slug (e.g. anthropic/claude-haiku-4-5, openai/gpt-4o). Optional: prompt, "
        "system_prompt; mcp_servers (inline servers the agent dials: stdio "
        '{"type":"stdio","id":...,"command":[...]} or http {"type":"http","id":...,'
        '"url":...}); skills (inline {"id":...,"files":{"SKILL.md":"..."}}); '
        "enabled_builtin_tools (subtractive allowlist over the agent's built-ins: "
        "absent = all, [] = none, subset = only those; same for "
        "enabled_builtin_{mcp_servers,subagents,skills}); output_schema (JSON Schema). "
        'Minimal: {"schema_version":"0.1","run_id":"demo",'
        '"model":"anthropic/claude-haiku-4-5","prompt":"Say hi."}'
    ),
    "trajectory": (
        "The Trajectory is the ordered event stream the agent emits. Ten v0.1 event "
        "types, all past-tense, all with source = avp://agent: run_requested, "
        "agent_described, agent_started, agent_stopped, assistant_message, "
        "tool_invoked, tool_returned, subagent_invoked, subagent_returned, "
        "error_occurred. A run opens run_requested -> agent_described -> "
        "agent_started and closes agent_stopped (with a stop reason). A turn is one "
        "assistant_message carrying avp.content, per-turn avp.usage, and avp.cost_usd. "
        "No cumulative totals are published; the consumer sums the per-turn deltas. "
        "Every event is a CloudEvents 1.0 envelope carrying OTel span ids "
        "(trace_id, span_id, parent_span_id) on its data."
    ),
    "cli": (
        "The `avp` CLI is a worked supervisor. avp init [benchmark] scaffolds a "
        "<name>.eval.json and seeds its commissions into ~/.avp/commissions/. "
        "avp eval run <config>.eval.json runs the commissions over the dataset and "
        "prints a ranked board (accuracy, pass-rate, $/run, turns/run). avp cm create "
        "builds a Commission into the library; avp cm check <id|file> validates a "
        "commission or a Commission JSON file. avp agent install <name> installs "
        "goose or claude-code. avp run --agent A --env E '<task>' drops an agent into "
        "an environment. Every run executes in a sandbox."
    ),
    "eval-config": (
        "An eval config is JSON: {name, agents, dataset, scorer, commissions}. "
        "dataset.source is 'inline' (items: [{id,prompt,expected}]), 'file' (a .jsonl "
        "path + input template + expected_field), or 'huggingface' (id + split + input "
        "+ expected_field; needs the huggingface extra). scorer.name is 'exact-match', "
        "'structural-match' (fraction of expected dict keys matched), "
        "'structural-fidelity' (rapidfuzz table-content match; needs the parsebench "
        "extra), or 'llm-judge' (needs the llm-judge extra + a key). commissions are "
        "ids resolved from the library; each commission carries its own model."
    ),
    "parsebench": (
        "ParseBench (PDF table/structure extraction) is run with: a huggingface "
        "dataset (id 'llamaindex/ParseBench', a split like 'table[:2]', an input URL "
        "template pointing at the PDF, an expected_field), the 'structural-fidelity' "
        "scorer, and a commission that wires a PDF-vision MCP server (stdio, e.g. "
        '{"type":"stdio","id":"pdf-vision","command":["uvx","--from",'
        '"git+https://github.com/I-CAN-hack/pdf-mcp.git","pdf-mcp"]}) plus the '
        "shell/write/edit built-in tools, and a prompt that says: download the PDF, "
        "render the page to an image, look at it, and reproduce the table as one HTML "
        "<table>. The scorer compares the agent's table content (markup stripped) to "
        "the expected markdown."
    ),
}
