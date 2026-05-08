from pathlib import Path

from e2n.cli import main


def test_converting_cli_reports_note_count(tmp_path: Path, capsys) -> None:
    source = tmp_path / "Enduring.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>Only Note</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>Body</en-note>]]></content>
  </note>
</en-export>
""",
        encoding="utf-8",
    )

    exit_code = main(["--converting", "-e", str(source), "-d", str(tmp_path / "processing")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Read 1 notes from" in captured.out
    assert "Successful extractions: 1" in captured.out
    assert "Extraction errors: 0" in captured.out
    assert "Processed 1 ENEX file(s)" in captured.out
