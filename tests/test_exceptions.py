from pathlib import Path

from e2n.exceptions import (
    EvernoteEmbeddedLinkRecord,
    ExceptionReason,
    UnsupportedAttributeGap,
    UnsupportedContentRecord,
    manual_correction_marker,
)


def test_manual_correction_marker_preserves_gap_details_and_resources() -> None:
    resource = Path("processing/Enduring/resources/example.bin")
    gap = UnsupportedAttributeGap(
        evernote_attribute="example-evernote-attribute",
        notion_target="database row property",
        documentation_gap="Notion API does not expose this target yet.",
        future_objective="Set this property automatically when the API supports it.",
        manual_correction_message="Manually copy the source value into the Notion row.",
        resource_paths=(resource,),
    )

    marker = manual_correction_marker("note_000001", "Example Note", gap)

    assert marker.note_id == "note_000001"
    assert marker.note_title == "Example Note"
    assert "example-evernote-attribute" in marker.marker_text
    assert "database row property" in marker.marker_text
    assert "Manually copy the source value" in marker.exception_message
    assert "Notion API does not expose this target yet" in marker.exception_message
    assert "Set this property automatically" in marker.exception_message
    assert marker.resource_paths == (resource,)


def test_unsupported_content_record_is_not_no_content() -> None:
    record = UnsupportedContentRecord(
        note_id="note_000002",
        note_title="Unsupported Note",
        error_comment="Encrypted Evernote block is not supported.",
    )

    assert record.reasons == (ExceptionReason.UNSUPPORTED_CONTENT,)
    assert ExceptionReason.NO_CONTENT not in record.reasons
    assert "Encrypted Evernote block" in record.marker_text


def test_evernote_embedded_link_record_preserves_link_text_and_value() -> None:
    record = EvernoteEmbeddedLinkRecord(
        note_id="note_000003",
        note_title="Linked Note",
        link_text="Original Title",
        link_value="evernote:///view/123/s1/guid/guid/",
    )

    assert record.reasons == (ExceptionReason.EVERNOTE_LINK,)
    assert record.link_text == "Original Title"
    assert record.link_value == "evernote:///view/123/s1/guid/guid/"
    assert "Original Title" in record.marker_text
