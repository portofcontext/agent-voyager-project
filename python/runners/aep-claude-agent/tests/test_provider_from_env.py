"""`gen_ai.provider.name` on `agent_started` reflects which cloud
actually served the run, not what the model name looks like.

Claude Agent SDK speaks Anthropic API on the wire regardless of model.
The backend is selected via env vars (`CLAUDE_CODE_USE_BEDROCK`,
`CLAUDE_CODE_USE_VERTEX`, `CLAUDE_CODE_USE_FOUNDRY`); with none set the
SDK calls Anthropic directly. Inferring provider from model-name prefix
(the previous behavior) was unreliable — `bedrock-claude-sonnet-4`
going through LiteLLM proxy is no more "AWS" than `claude-sonnet-4`
direct. Tag from env vars instead.
"""

from __future__ import annotations

from aep_claude_agent.translator import _provider_from_env


def test_default_is_anthropic(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
    assert _provider_from_env() == "anthropic"


def test_bedrock_env_var_returns_aws_bedrock(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
    assert _provider_from_env() == "aws.bedrock"


def test_vertex_env_var_returns_gcp_vertex_ai(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
    assert _provider_from_env() == "gcp.vertex_ai"


def test_foundry_env_var_returns_azure_ai_inference(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")
    assert _provider_from_env() == "azure.ai.inference"


def test_env_var_set_to_zero_does_not_count_as_enabled(monkeypatch) -> None:
    """The SDK convention is `=1` to enable. Don't treat any other value
    as enabling — if a user sets the var to `0`, that's not enabling
    anything."""
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "0")
    monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_USE_FOUNDRY", raising=False)
    assert _provider_from_env() == "anthropic"


def test_bedrock_takes_precedence_when_multiple_set(monkeypatch) -> None:
    """The SDK env vars are mutually exclusive; if a misconfigured
    deployment sets multiple, we pick a stable order rather than
    silently dropping the signal. Bedrock first matches the SDK's own
    documented precedence."""
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    monkeypatch.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")
    assert _provider_from_env() == "aws.bedrock"
