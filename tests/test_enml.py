from e2n.enml import ContentSegment, chunk_text, plan_enml_segments


def test_plan_enml_segments_breaks_text_around_non_text_items() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<en-note>Before <a href="evernote:/view/123/s1/guid/guid/">Linked Note</a> after
<en-media hash="abc123" type="application/pdf"/> done</en-note>"""

    assert plan_enml_segments(content) == (
        ContentSegment(kind="text", text="Before"),
        ContentSegment(kind="evernote_link", text="Linked Note", value="evernote:/view/123/s1/guid/guid/"),
        ContentSegment(kind="text", text="after"),
        ContentSegment(kind="resource", text="en-media", value="abc123", mime_type="application/pdf"),
        ContentSegment(kind="text", text="done"),
    )


def test_plan_enml_segments_http_link_stays_inline() -> None:
    content = '<en-note>Visit <a href="https://example.com">Example</a> today</en-note>'
    assert plan_enml_segments(content) == (
        ContentSegment(kind="text", text="Visit"),
        ContentSegment(kind="http_link", text="Example", value="https://example.com"),
        ContentSegment(kind="text", text="today"),
    )


def test_plan_enml_segments_table_becomes_own_segment() -> None:
    content = "<en-note>Before<table><tr><td>Cell</td></tr></table>After</en-note>"
    segments = plan_enml_segments(content)
    kinds = [s.kind for s in segments]
    assert "table" in kinds
    text_segments = [s for s in segments if s.kind == "text"]
    assert any("Before" in s.text for s in text_segments)
    assert any("After" in s.text for s in text_segments)


def test_plan_enml_segments_image_resource_carries_mime_type() -> None:
    content = '<en-note><en-media hash="imgabc" type="image/png"/></en-note>'
    (segment,) = plan_enml_segments(content)
    assert segment.kind == "resource"
    assert segment.mime_type == "image/png"
    assert segment.value == "imgabc"


def test_plan_enml_segments_chunks_large_text_blocks() -> None:
    assert plan_enml_segments("<en-note>one two three four</en-note>", text_block_limit=7) == (
        ContentSegment(kind="text", text="one two"),
        ContentSegment(kind="text", text="three"),
        ContentSegment(kind="text", text="four"),
    )


def test_chunk_text_splits_long_words() -> None:
    assert chunk_text("abcdef ghi", limit=3) == ("abc", "def", "ghi")
