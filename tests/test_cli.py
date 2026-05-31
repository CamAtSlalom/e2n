from pathlib import Path
import sqlite3

from e2n.cli import main
from e2n.enex import extract_enex_notes
from e2n.notion import NotionBootstrapResult, NotionDatabaseRef, NotionPageRef


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


def test_converting_cli_processes_directory_with_workers(tmp_path: Path, capsys) -> None:
    source_directory = tmp_path / "exports"
    source_directory.mkdir()
    for name in ("First.enex", "Second.enex"):
        (source_directory / name).write_text(
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

    exit_code = main(
        ["--converting", "-e", str(source_directory), "-d", str(tmp_path / "processing"), "--workers", "2"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Processed 2 ENEX file(s)" in captured.out
    assert (tmp_path / "processing" / "First" / "success.txt").exists()
    assert (tmp_path / "processing" / "Second" / "success.txt").exists()


class _FakeNotionClient:
    def __init__(self) -> None:
        self.created_rows: list[tuple[str, str, tuple[str, ...]]] = []
        self.archived_pages: list[str] = []

    def create_database_row(self, database_id: str, title: str, tags: tuple[str, ...] | list[str]) -> NotionPageRef:
        normalized = tuple(tags)
        page_id = f"page-{len(self.created_rows) + 1}"
        self.created_rows.append((database_id, title, normalized))
        return NotionPageRef(page_id=page_id, title=title, url=None, parent_page_id=None)

    def archive_page(self, page_id: str) -> NotionPageRef:
        self.archived_pages.append(page_id)
        return NotionPageRef(page_id=page_id, title="Archived", url=None, parent_page_id=None)


def _write_single_note_source(tmp_path: Path) -> Path:
    source = tmp_path / "Enduring.enex"
    source.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<en-export>
  <note>
    <title>Only Note</title>
    <content><![CDATA[<?xml version="1.0" encoding="UTF-8"?><en-note>Body</en-note>]]></content>
    <tag>Project</tag>
  </note>
</en-export>
""",
        encoding="utf-8",
    )
    return source


def _latest_run_id(state_path: Path) -> str:
    with sqlite3.connect(state_path) as connection:
        row = connection.execute("SELECT run_id FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
    assert row is not None
    return str(row[0])


def test_notion_import_cli_uploads_rows_with_resume(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_single_note_source(tmp_path)
    processing = tmp_path / "processing"
    extract_enex_notes(source, processing)

    fake_notion = _FakeNotionClient()
    bootstrap = NotionBootstrapResult(
        root=NotionPageRef(page_id="root", title="Root", url=None, parent_page_id=None),
        converted=NotionPageRef(page_id="converted", title="Evernote Import", url=None, parent_page_id="root"),
        exceptions=NotionPageRef(
            page_id="exceptions", title="Evernote Import Exceptions", url=None, parent_page_id="root"
        ),
    )

    monkeypatch.setattr("e2n.cli.bootstrap_notion_pages", lambda notion_key, root_title=None: bootstrap)
    monkeypatch.setattr("e2n.cli.NotionClient", lambda notion_key: fake_notion)
    monkeypatch.setattr(
        "e2n.cli.ensure_import_database",
        lambda client, parent_page_id, database_title: NotionDatabaseRef(
            database_id="database-1", title=database_title, url=None, parent_page_id=parent_page_id
        ),
    )

    first_exit = main(["--notion-import", "-e", str(source), "-d", str(processing), "-k", "notion-key"])
    second_exit = main(["--notion-import", "-e", str(source), "-d", str(processing), "-k", "notion-key"])
    resume_exit = main(["--notion-import", "-e", str(source), "-d", str(processing), "-k", "notion-key", "--resume"])

    captured = capsys.readouterr()
    assert first_exit == 0
    assert second_exit == 1
    assert resume_exit == 0
    assert "Imported source Enduring.enex: processed 1 operation(s), committed=1 failed=0 pending=0" in captured.out
    assert len(fake_notion.created_rows) == 1


def test_notion_import_cli_wipe_remote_archives_and_clears_map(monkeypatch, tmp_path: Path, capsys) -> None:
    source = _write_single_note_source(tmp_path)
    processing = tmp_path / "processing"
    output = processing / "Enduring"
    extract_enex_notes(source, processing)
    run_id = _latest_run_id(output / "state.db")

    fake_notion = _FakeNotionClient()
    bootstrap = NotionBootstrapResult(
        root=NotionPageRef(page_id="root", title="Root", url=None, parent_page_id=None),
        converted=NotionPageRef(page_id="converted", title="Evernote Import", url=None, parent_page_id="root"),
        exceptions=NotionPageRef(
            page_id="exceptions", title="Evernote Import Exceptions", url=None, parent_page_id="root"
        ),
    )
    monkeypatch.setattr("e2n.cli.bootstrap_notion_pages", lambda notion_key, root_title=None: bootstrap)
    monkeypatch.setattr("e2n.cli.NotionClient", lambda notion_key: fake_notion)
    monkeypatch.setattr(
        "e2n.cli.ensure_import_database",
        lambda client, parent_page_id, database_title: NotionDatabaseRef(
            database_id="database-1", title=database_title, url=None, parent_page_id=parent_page_id
        ),
    )

    import_exit = main(["--notion-import", "-e", str(source), "-d", str(processing), "-k", "notion-key"])
    wipe_exit = main(
        [
            "--notion-import",
            "-e",
            str(source),
            "-d",
            str(processing),
            "-k",
            "notion-key",
            "--wipe-remote",
            run_id,
        ]
    )

    captured = capsys.readouterr()
    with sqlite3.connect(output / "state.db") as connection:
        remaining = connection.execute("SELECT COUNT(*) FROM notion_map").fetchone()

    assert import_exit == 0
    assert wipe_exit == 0
    assert remaining is not None
    assert remaining[0] == 0
    assert fake_notion.archived_pages == ["page-1"]
    assert f"Wiped remote mappings for run {run_id}: archived 1 page(s), cleared 1 mapping(s)" in captured.out


def test_notion_import_cli_wipe_local_removes_processing_directory(tmp_path: Path, capsys) -> None:
    source = _write_single_note_source(tmp_path)
    processing = tmp_path / "processing"
    output = processing / "Enduring"
    extract_enex_notes(source, processing)
    run_id = _latest_run_id(output / "state.db")

    exit_code = main(
        [
            "--notion-import",
            "-e",
            str(source),
            "-d",
            str(processing),
            "--wipe-local",
            run_id,
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert not output.exists()
    assert f"Wiped local processing output for run {run_id}: {output}" in captured.out
