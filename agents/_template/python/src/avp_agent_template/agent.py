"""The adapter: harness events in, Recorder calls out.

`describe` and `run` are all the stock entrypoint (`avp.agent_cli`) needs.
"""

from __future__ import annotations

from importlib.metadata import version

from avp.commission import Commission
from avp.descriptor import AgentDescriptor, ToolDecl
from avp.preflight import preflight
from avp.pricing import load_default_prices
from avp.recorder import Recorder
from avp.sink import EventSink
from avp.trajectory import ErrorCode, StopReason
from avp_agent_template import harness, translate
from avp_agent_template.commission import AGENT_NAME, BUILTIN_TOOLS, from_commission

# The package version, so it can't drift from pyproject.toml (Commission
# `agent_versions` pins and the release guard both compare against it).
AGENT_VERSION = version(AGENT_NAME)
# The provider bare model names resolve under in the price table.
PROVIDER = "openai"


def describe() -> AgentDescriptor:
    """What the agent ships with, before any Commission."""
    return AgentDescriptor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        spec_version="0.1",
        tools=[ToolDecl(name=name) for name in BUILTIN_TOOLS],
    )


async def run(commission: Commission, sink: EventSink) -> None:
    rec = Recorder(sink, run_id=commission.run_id, provider=PROVIDER, prices=load_default_prices())
    await rec.prelude(commission, describe())
    # The spec's pre-turn Commission checks (version pin, allow-list keys and
    # names); add harness-specific refusals (unreachable provider/model) here.
    if failure := preflight(
        commission, agent_name=AGENT_NAME, agent_version=AGENT_VERSION, tools=BUILTIN_TOOLS
    ):
        await rec.error(*failure)
        await rec.stop(StopReason.error)
        return
    config = from_commission(commission)
    await rec.start(
        request_model=config.model,
        prompt=config.prompt,
        system_prompt=config.system_prompt,
        tools=[ToolDecl(name=name) for name in config.tools],
    )
    try:
        async for event in harness.stream(config):
            if event["kind"] == "message":
                await rec.assistant(
                    translate.content(event),
                    translate.usage(event["usage"]),
                    model=config.model,
                )
            elif event["kind"] == "tool_result":
                await rec.tool_result(event["call_id"], event["output"], is_error=event["error"])
            elif event["kind"] == "done":
                await rec.stop(translate.stop_reason(event["status"]), event["output"])
    except Exception as exc:
        await rec.error(ErrorCode.agent_crash, str(exc) or type(exc).__name__)
        await rec.stop(StopReason.error)
        raise
    await rec.stop(StopReason.converged)  # no-op when the harness already ended the run
