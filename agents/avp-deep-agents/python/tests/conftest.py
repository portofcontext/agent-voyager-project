"""A scripted chat model for the integration tests: LangChain's `GenericFakeChatModel`
answering from a script, with tool binding accepted and every request kept.

A script entry is an `AIMessage` (returned), an exception (raised), or a
callable of the request's messages returning either."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from avp_deep_agents import commission as cm


def usage(input_tokens: int = 1000, output_tokens: int = 50, cache_read: int = 400) -> dict:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "input_token_details": {"cache_read": cache_read},
        "output_token_details": {"reasoning": 10},
    }


def reply(text: str = "", *calls: tuple[str, str, dict], **meta: Any) -> AIMessage:
    """One model response: text plus `(call_id, tool, args)` tool calls."""
    return AIMessage(
        content=text,
        tool_calls=[{"id": i, "name": n, "args": a, "type": "tool_call"} for i, n, a in calls],
        usage_metadata=usage(),
        response_metadata={"model_name": "gpt-4o-mini-2024-07-18", "finish_reason": "stop", **meta},
    )


class ScriptedModel(GenericFakeChatModel):
    requests: list[list[BaseMessage]] = Field(default_factory=list)
    tool_sets: list[list[str]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **_: Any) -> ScriptedModel:
        self.tool_sets.append([t.get("name") if isinstance(t, dict) else t.name for t in tools])
        return self

    def _next(self, messages: list[BaseMessage]) -> Any:
        self.requests.append(messages)
        item = next(self.messages)
        return item(messages) if callable(item) else item

    def _generate(self, messages: list[BaseMessage], *_: Any, **__: Any) -> ChatResult:
        item = self._next(messages)
        if isinstance(item, BaseException):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])

    async def _agenerate(self, messages: list[BaseMessage], *_: Any, **__: Any) -> ChatResult:
        item = self._next(messages)
        if asyncio.iscoroutine(item):
            item = await item
        if isinstance(item, BaseException):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Callable[..., ScriptedModel]:
    """Install a scripted model as the run's chat model."""

    def install(*steps: Any) -> ScriptedModel:
        model = ScriptedModel(messages=iter(steps))
        monkeypatch.setattr(cm, "chat_model", lambda commission: model)
        return model

    return install
