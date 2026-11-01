import json

from avp.agent_cli import main
from avp.descriptor import AgentDescriptor
from avp_pydantic_ai.cli import describe, run


def test_describe_writes_a_valid_descriptor(tmp_path):
    out = tmp_path / "descriptor.json"
    assert main(run=run, describe=describe, argv=["describe", "--out", str(out)]) == 0
    descriptor = AgentDescriptor.model_validate(json.loads(out.read_text()))
    assert descriptor.agent_name == "avp-pydantic-ai"
    assert {m.provider for m in descriptor.supported_models or []} == {
        "anthropic",
        "google",
        "openai",
    }
