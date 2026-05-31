from pathlib import Path
import sqlite3

from e2n.enex import ExtractedNote
from e2n.exception_rebuild import rebuild_exceptions_for_source
from e2n.state import ProcessingStateStore
from e2n.notion import EXCEPTION_KEY_PROPERTY, EXCEPTION_STATUS_PROPERTY, NotionPageRef


class FakeNotionForRebuild:
    def __init__(self) -> None:
        self.created_rows: list[tuple[str, dict]] = []
        self.updated_rows: list[tuple[str, dict]] = []
        self._existing_exception_page_id = "exc-page-1"

    def list_block_children(self, block_id: str) -> list[dict]:
        if block_id == "page-note-1":
            return [
                {
                    "id": "block-1",
                    "type": "callout",
                    "has_children": False,
                    "callout": {
                        "rich_text": [
                            {
                                "plain_text": "Evernote link requires manual resolution: Target Note",
                            }
                        ]
                    },
                }
            ]
        return []

    def search_pages(self, query: str | None = None) -> list[NotionPageRef]:
        # Existing stale exception row for the same source file, should be closed.
        return [
            NotionPageRef(
                page_id=self._existing_exception_page_id,
                title="Stale Exception",
                url=None,
                parent_page_id=None,
                parent_database_id="db-exceptions",
                parent_type="database_id",
            )
        ]

    def retrieve_page_raw(self, page_id: str) -> dict:
        assert page_id == self._existing_exception_page_id
        return {
            "id": page_id,
            "properties": {
                EXCEPTION_KEY_PROPERTY: {"rich_text": [{"plain_text": "stale-key"}]},
                "Source File": {"rich_text": [{"plain_text": "Source.enex"}]},
            },
        }

    def create_database_page(self, database_id: str, properties: dict) -> None:
        self.created_rows.append((database_id, properties))
        return None

    def update_page_properties(self, page_id: str, properties: dict) -> None:
        self.updated_rows.append((page_id, properties))
        return None


def test_rebuild_from_notion_scans_markers_and_syncs_exception_rows(tmp_path: Path) -> None:
    processing = tmp_path / "processing"
    output_dir = processing / "Source"
    state = ProcessingStateStore(output_dir / "state.db")

    run_id = state.begin_run(source_path=tmp_path / "Source.enex", output_directory=output_dir)
    note = ExtractedNote(
        note_id="note_000001",
        title="Example Note",
        path=output_dir / "notes" / "note_000001.enex",
    )
    state.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "Source.enex", status="extracted")
    operation_id = state.enqueue_operation(
        run_id=run_id,
        note_id=note.note_id,
        operation_type="create_database_row",
        payload={"database_id": "db-1", "title": note.title, "tags": []},
        idempotency_key="note_000001:create_database_row",
    )
    state.mark_operation_committed(operation_id, notion_object_id="page-note-1")
    state.close()

    fake_notion = FakeNotionForRebuild()
    summary = rebuild_exceptions_for_source(
        source_path=tmp_path / "Source.enex",
        processing_directory=processing,
        apply=True,
        review_version="phase2a-test",
        from_notion=True,
        notion=fake_notion,  # type: ignore[arg-type]
        sync_notion_exceptions=True,
        exception_database_id="db-exceptions",
    )

    assert summary.total_notes == 1
    assert summary.total_exceptions == 1
    assert summary.review_passed_with_open_exceptions == 1

    # One fresh exception row should be upserted to Notion exceptions DB.
    assert len(fake_notion.created_rows) == 1
    created_db_id, created_props = fake_notion.created_rows[0]
    assert created_db_id == "db-exceptions"
    assert created_props[EXCEPTION_STATUS_PROPERTY]["select"]["name"] == "Open"

    # Existing stale row should be closed.
    assert len(fake_notion.updated_rows) == 1
    updated_page_id, updated_props = fake_notion.updated_rows[0]
    assert updated_page_id == "exc-page-1"
    assert updated_props[EXCEPTION_STATUS_PROPERTY]["select"]["name"] == "Closed"

    with sqlite3.connect(output_dir / "state.db") as connection:
        projection_count = connection.execute("SELECT COUNT(*) FROM exception_projection").fetchone()
        review_result = connection.execute(
            "SELECT review_result FROM note_reviews WHERE run_id = ? AND note_id = ?",
            (run_id, "note_000001"),
        ).fetchone()

    assert projection_count is not None
    assert projection_count[0] == 1
    assert review_result is not None
    assert review_result[0] == "review_passed_with_open_exceptions"
