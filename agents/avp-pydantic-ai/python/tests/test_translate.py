from pydantic_ai import (
    BinaryContent,
    FilePart,
    ModelResponse,
    NativeToolCallPart,
    NativeToolReturnPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)
from pydantic_ai.messages import (
    Citation,
    CompactionPart,
    ContentCitationAnchor,
    WebCitationSource,
)

from avp.recorder import Image
from avp_pydantic_ai import translate


def _parts(parts: list) -> list[dict]:
    def image(data: bytes, media_type: str) -> Image:
        return Image.model_validate({"path": "images/x.png", "media_type": media_type})

    return [
        p.model_dump(exclude_defaults=True, exclude_none=True)
        for p in translate.parts(ModelResponse(parts=parts), image)
    ]


def test_tools_the_service_runs_are_server_side_calls_with_their_results() -> None:
    assert _parts(
        [
            NativeToolCallPart("web_search", {"query": "avp"}, tool_call_id="s1"),
            NativeToolReturnPart("web_search", [{"url": "https://a.example"}], tool_call_id="s1"),
            ToolCallPart("read_file", {"path": "a.py"}, tool_call_id="c1"),
        ]
    ) == [
        {"id": "s1", "name": "web_search", "arguments": {"query": "avp"}, "server_side": True},
        {
            "call_id": "s1",
            "content": '[{"url": "https://a.example"}]',
            "structured_content": [{"url": "https://a.example"}],
        },
        {"id": "c1", "name": "read_file", "arguments": {"path": "a.py"}},
    ]


def test_an_image_file_is_an_image_part_and_other_parts_are_left_out() -> None:
    image = FilePart(BinaryContent(data=b"\x89PNG", media_type="image/png"))
    pdf = FilePart(BinaryContent(data=b"%PDF", media_type="application/pdf"))
    assert _parts([TextPart("see"), image, pdf, CompactionPart(content="summary")]) == [
        {"text": "see"},
        {"path": "images/x.png", "media_type": "image/png"},
    ]


def test_redacted_thinking_is_encrypted_reasoning() -> None:
    assert _parts([ThinkingPart("first", signature="a"), ThinkingPart("", signature="sealed")]) == [
        {"text": "first", "signature": "a"},
        {"encrypted_content": "sealed"},
    ]


def test_citations_keep_their_sources() -> None:
    source = WebCitationSource("https://a.example", title="A", excerpts=["cited"])
    text = TextPart(
        "AVP is a spec.",
        citations=[Citation([source], anchor=ContentCitationAnchor(start=0, end=3))],
    )
    assert _parts([text])[0]["citations"] == [
        {
            "type": "web",
            "cited_text": "cited",
            "start_index": 0,
            "end_index": 3,
            "source_url": "https://a.example",
            "source_title": "A",
        }
    ]
