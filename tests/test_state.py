from pathlib import Path
import sqlite3

from e2n.enex import ExtractedNote
from e2n.operation_queue import NotionRateLimiter, ResumableOperationQueue
from e2n.state import (
    OPERATION_STATUS_FAILED,
    OPERATION_STATUS_IN_PROGRESS,
    OPERATION_STATUS_PENDING,
    ProcessingStateStore,
)


def test_state_store_records_run_and_notes(tmp_path: Path) -> None:
    store = ProcessingStateStore(tmp_path / "processing" / "state.db")
    note = ExtractedNote(
        note_id="note_000001",
        title="Sample",
        path=tmp_path / "processing" / "notes" / "note_000001.enex",
        tags=("A", "B"),
        exception_reasons=(),
    )

    run_id = store.begin_run(source_path=tmp_path / "sample.enex", output_directory=tmp_path / "processing")
    store.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "sample.enex", status="extracted")
    store.close()

    with sqlite3.connect(tmp_path / "processing" / "state.db") as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()
        note_row = connection.execute("SELECT note_id, status FROM notes").fetchone()

    assert run_count is not None
    assert run_count[0] == 1
    assert note_row is not None
    assert note_row[0] == "note_000001"
    assert note_row[1] == "extracted"


def test_resumable_queue_commits_and_writes_checkpoint(tmp_path: Path) -> None:
    store = ProcessingStateStore(tmp_path / "processing" / "state.db")
    note = ExtractedNote(
        note_id="note_000001",
        title="Upload Me",
        path=tmp_path / "processing" / "notes" / "note_000001.enex",
        tags=(),
        exception_reasons=(),
    )
    run_id = store.begin_run(source_path=tmp_path / "source.enex", output_directory=tmp_path / "processing")
    store.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "source.enex", status="extracted")
    store.enqueue_operation(
        run_id=run_id,
        note_id=note.note_id,
        operation_type="create_page",
        payload={"title": note.title},
        idempotency_key="note_000001:create_page",
    )

    queue = ResumableOperationQueue(store, rate_limiter=NotionRateLimiter(max_operations=3, per_seconds=1.0))
    processed = queue.run_once(run_id=run_id, handler=lambda operation: f"notion-{operation.note_id}")

    assert processed is not None

    with sqlite3.connect(tmp_path / "processing" / "state.db") as connection:
        operation_row = connection.execute("SELECT status FROM operations").fetchone()
        checkpoint_row = connection.execute("SELECT last_committed_operation_id FROM checkpoints").fetchone()
        notion_map_row = connection.execute("SELECT notion_object_id FROM notion_map").fetchone()

    assert operation_row is not None
    assert operation_row[0] == "committed"
    assert checkpoint_row is not None
    assert checkpoint_row[0] is not None
    assert notion_map_row is not None
    assert notion_map_row[0] == "notion-note_000001"
    store.close()


def test_resumable_queue_marks_failed_operation(tmp_path: Path) -> None:
    store = ProcessingStateStore(tmp_path / "processing" / "state.db")
    note = ExtractedNote(
        note_id="note_000001",
        title="Upload Me",
        path=tmp_path / "processing" / "notes" / "note_000001.enex",
        tags=(),
        exception_reasons=(),
    )
    run_id = store.begin_run(source_path=tmp_path / "source.enex", output_directory=tmp_path / "processing")
    store.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "source.enex", status="extracted")
    store.enqueue_operation(
        run_id=run_id,
        note_id=note.note_id,
        operation_type="create_page",
        payload={"title": note.title},
        idempotency_key="note_000001:create_page",
    )

    queue = ResumableOperationQueue(store, rate_limiter=NotionRateLimiter(max_operations=3, per_seconds=1.0))

    def fail_handler(_operation: object) -> str:
        raise RuntimeError("temporary Notion failure")

    operation = queue.run_once(run_id=run_id, handler=fail_handler)

    assert operation is not None

    retry = store.claim_next_operation(run_id)
    assert retry is None

    with sqlite3.connect(tmp_path / "processing" / "state.db") as connection:
        operation_row = connection.execute(
            "SELECT status, attempt_count, last_error FROM operations"
        ).fetchone()

    assert operation_row is not None
    assert operation_row[0] == OPERATION_STATUS_FAILED
    assert operation_row[1] == 1
    assert operation_row[2] == "temporary Notion failure"
    assert operation.status == OPERATION_STATUS_IN_PROGRESS
    store.close()


def test_reset_run_clears_checkpoint_and_operation_errors(tmp_path: Path) -> None:
    store = ProcessingStateStore(tmp_path / "processing" / "state.db")
    note = ExtractedNote(
        note_id="note_000001",
        title="Retry",
        path=tmp_path / "processing" / "notes" / "note_000001.enex",
        tags=(),
        exception_reasons=(),
    )
    run_id = store.begin_run(source_path=tmp_path / "source.enex", output_directory=tmp_path / "processing")
    store.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "source.enex", status="extracted")
    operation_id = store.enqueue_operation(
        run_id=run_id,
        note_id=note.note_id,
        operation_type="create_page",
        payload={"title": note.title},
        idempotency_key="note_000001:create_page",
    )
    store.mark_operation_failed(operation_id, "temp", retry_after_seconds=5)
    store.mark_operation_committed(operation_id, notion_object_id="notion-note_000001")

    changed = store.reset_run(run_id)

    assert changed == 1
    counts = store.count_operations_by_status(run_id)
    assert counts.get(OPERATION_STATUS_PENDING) == 1
    assert store.list_notion_object_ids(run_id) == []
    store.close()


def test_wipe_local_run_deletes_state_rows(tmp_path: Path) -> None:
    store = ProcessingStateStore(tmp_path / "processing" / "state.db")
    note = ExtractedNote(
        note_id="note_000001",
        title="Delete Me",
        path=tmp_path / "processing" / "notes" / "note_000001.enex",
        tags=(),
        exception_reasons=(),
    )
    run_id = store.begin_run(source_path=tmp_path / "source.enex", output_directory=tmp_path / "processing")
    store.upsert_note(run_id=run_id, note=note, source_path=tmp_path / "source.enex", status="extracted")

    assert store.run_exists(run_id)
    store.wipe_local_run(run_id)
    assert not store.run_exists(run_id)
    store.close()
