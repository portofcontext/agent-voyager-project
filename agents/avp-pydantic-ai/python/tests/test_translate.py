from pydantic_ai import (
    BinaryContent,
    FilePart,
    NativeToolCallPart,
    NativeToolReturnPart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.messages import (
    Citation,
    CompactionPart,
    ContentCitationAnchor,
    WebCitationSource,
)

from avp_pydantic_ai import translate


def _dump(parts: list) -> list[dict]:
    return [b.model_dump(exclude_none=True) for b in translate.content(parts)]


def test_tools_the_service_runs_are_server_tool_blocks() -> None:
    assert _dump(
        [
            NativeToolCallPart("web_search", {"query": "avp"}, tool_call_id="s1"),
            NativeToolReturnPart("web_search", [{"url": "https://a.example"}], tool_call_id="s1"),
            ToolCallPart("read_file", {"path": "a.py"}, tool_call_id="c1"),
        ]
    ) == [
        {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "avp"}},
        {
            "type": "server_tool_result",
            "tool_use_id": "s1",
            "name": "web_search",
            "content": [{"url": "https://a.example"}],
        },
        {"type": "tool_use", "id": "c1", "name": "read_file", "input": {"path": "a.py"}},
    ]


def test_an_image_file_is_an_image_block_and_other_parts_are_left_out() -> None:
    image = FilePart(BinaryContent(data=b"\x89PNG", media_type="image/png"))
    pdf = FilePart(BinaryContent(data=b"%PDF", media_type="application/pdf"))
    assert _dump([image, pdf, CompactionPart(content="summary")]) == [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw=="},
        }
    ]


def test_citations_keep_their_sources() -> None:
    source = WebCitationSource("https://a.example", title="A", excerpts=["cited"])
    text = TextPart(
        "AVP is a spec.",
        citations=[Citation([source], anchor=ContentCitationAnchor(start=0, end=3))],
    )
    assert _dump([text])[0]["citations"] == [
        {
            "type": "web",
            "cited_text": "cited",
            "start_index": 0,
            "end_index": 3,
            "source_url": "https://a.example",
            "source_title": "A",
        }
    ]
