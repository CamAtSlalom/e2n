from pathlib import Path

from e2n.enex import discover_enex_sources, extract_enex_notes


def test_extract_enex_notes_creates_processing_files(tmp_path: Path) -> None:
    source = tmp_path / "Enduring.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>First Note</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>First</en-note>]]></content>
  </note>
  <note>
    <title>Second Note</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>Second</en-note>]]></content>
  </note>
</en-export>
""",
        encoding="utf-8",
    )

    result = extract_enex_notes(source, tmp_path / "processing")

    output_directory = tmp_path / "processing" / "Enduring"
    assert result.total_notes == 2
    assert result.success_count == 2
    assert result.error_count == 0
    assert output_directory.is_dir()
    assert (output_directory / "master.txt").read_text(encoding="utf-8").count("\n") == 2
    assert (output_directory / "success.txt").read_text(encoding="utf-8").count("\n") == 2
    assert (output_directory / "errors.txt").read_text(encoding="utf-8") == ""
    assert (output_directory / "resources").is_dir()
    assert (output_directory / "notes" / "note_000001.enex").exists()
    assert (output_directory / "notes" / "note_000002.enex").exists()


def test_discover_enex_sources_returns_sorted_directory_children(tmp_path: Path) -> None:
    source_directory = tmp_path / "exports"
    source_directory.mkdir()
    second = source_directory / "Second.enex"
    first = source_directory / "First.enex"
    ignored = source_directory / "Ignored.txt"
    second.write_text("<en-export></en-export>", encoding="utf-8")
    first.write_text("<en-export></en-export>", encoding="utf-8")
    ignored.write_text("ignored", encoding="utf-8")

    assert discover_enex_sources(source_directory) == [first.resolve(), second.resolve()]
