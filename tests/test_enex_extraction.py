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
    assert (output_directory / "exceptions.txt").read_text(encoding="utf-8") == ""
    assert (output_directory / "state.db").exists()
    assert (output_directory / "resources").is_dir()
    assert (output_directory / "notes" / "note_000001.enex").exists()
    assert (output_directory / "notes" / "note_000002.enex").exists()


def test_extract_enex_notes_records_empty_title_no_content_and_tags(tmp_path: Path) -> None:
    source = tmp_path / "Issues.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>   </title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note></en-note>]]></content>
    <tag>Project</tag>
    <tag>Important</tag>
    <tag>Project</tag>
  </note>
  <note>
    <title>Has Resource</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note></en-note>]]></content>
    <resource>
      <data encoding="base64">AA==</data>
    </resource>
  </note>
</en-export>
""",
        encoding="utf-8",
    )

    result = extract_enex_notes(source, tmp_path / "processing")

    output_directory = tmp_path / "processing" / "Issues"
    master_lines = (output_directory / "master.txt").read_text(encoding="utf-8").splitlines()
    exception_lines = (output_directory / "exceptions.txt").read_text(encoding="utf-8").splitlines()

    assert result.total_notes == 2
    assert master_lines[0].split("\t")[:5] == [
        "note_000001",
        "Empty Title",
        str(output_directory / "notes" / "note_000001.enex"),
        "Project,Important",
        "Empty Title,No Content",
    ]
    assert master_lines[1].endswith("\t\t")
    assert len(exception_lines) == 1
    assert exception_lines[0].split("\t") == [
        "note_000001",
        "Empty Title",
        "Empty Title,No Content",
        str(source.resolve()),
        "",
        "",
        "",
    ]


def test_extract_enex_notes_records_evernote_embedded_links(tmp_path: Path) -> None:
    source = tmp_path / "Links.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>Link Note</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
      <en-note>
        <div>See <a href="evernote:///view/123/s1/guid/guid/">Original Evernote Note</a></div>
        <div>Also <a href="evernote:/view/123/s1/guid2/guid2/">Single Slash</a></div>
        <div>And <a href="evernote://view/123/s1/guid3/guid3/">Double Slash</a></div>
        <div>Plain <a href="evernote:view/123/s1/guid4/guid4/">No Slash</a></div>
      </en-note>]]></content>
  </note>
</en-export>
""",
        encoding="utf-8",
    )

    extract_enex_notes(source, tmp_path / "processing")

    exception_lines = (tmp_path / "processing" / "Links" / "exceptions.txt").read_text(encoding="utf-8").splitlines()

    assert exception_lines == [
        "\t".join(["note_000001", "Link Note", "Evernote Link", str(source.resolve()), "", text, value])
        for text, value in (
            ("Original Evernote Note", "evernote:///view/123/s1/guid/guid/"),
            ("Single Slash", "evernote:/view/123/s1/guid2/guid2/"),
            ("Double Slash", "evernote://view/123/s1/guid3/guid3/"),
            ("No Slash", "evernote:view/123/s1/guid4/guid4/"),
        )
    ]


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
