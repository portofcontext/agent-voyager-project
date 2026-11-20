"""Claude content blocks and usage to Recorder parts."""

import pytest

from avp.recorder import Call, Reasoning, ServerResult, Text, Usage
from avp_claude_agent_sdk import translate


def test_blocks_become_parts_in_order():
    parts = translate.parts(
        [
            {"type": "thinking", "thinking": "Look it up.", "signature": "sig"},
            {"type": "redacted_thinking", "data": "secret"},
            {
                "type": "server_tool_use",
                "id": "search",
                "name": "web_search",
                "input": {"query": "avp"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "search",
                "content": [{"type": "web_search_result", "url": "https://a.example"}],
            },
            {
                "type": "text",
                "text": "Found it.",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "cited_text": "it",
                        "url": "https://a.example",
                        "title": "A",
                        "encrypted_index": "x",
                    }
                ],
            },
            {"type": "tool_use", "id": "call", "name": "Bash", "input": {"command": "ls"}},
        ]
    )
    assert [type(p) for p in parts] == [Reasoning, Reasoning, Call, ServerResult, Text, Call]
    assert parts[0] == Reasoning(text="Look it up.", signature="sig")
    assert parts[1] == Reasoning(encrypted_content="secret")
    assert isinstance(parts[2], Call) and isinstance(parts[5], Call)
    assert parts[2].server_side and not parts[5].server_side
    assert isinstance(parts[3], ServerResult)
    assert parts[3].structured_content == [
        {"type": "web_search_result", "url": "https://a.example"}
    ]
    assert isinstance(parts[4], Text) and parts[4].citations is not None
    citation = parts[4].citations[0]
    assert (citation.source_url, citation.source_title, citation.cited_text) == (
        "https://a.example",
        "A",
        "it",
    )


def test_server_tool_errors_are_errors():
    [_, result] = translate.parts(
        [
            {"type": "server_tool_use", "id": "s", "name": "web_fetch", "input": {}},
            {
                "type": "web_fetch_tool_result",
                "tool_use_id": "s",
                "content": {"type": "web_fetch_tool_error", "error_code": "url_not_accessible"},
            },
        ]
    )
    assert isinstance(result, ServerResult) and result.is_error


def test_unknown_blocks_are_refused():
    with pytest.raises(ValueError, match="unsupported Claude content block"):
        translate.parts([{"type": "container_upload"}])


def test_usage_counts_cache_tokens_in_the_prompt():
    native = {
        "input_tokens": 10,
        "output_tokens": 8,
        "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 30,
        "output_tokens_details": {"thinking_tokens": 3},
    }
    assert translate.usage(native) == Usage(
        prompt_tokens=60,
        completion_tokens=8,
        cached_tokens=20,
        cache_creation_input_tokens=30,
        reasoning_output_tokens=3,
    )
