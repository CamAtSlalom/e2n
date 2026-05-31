"""Durable local state and operation tracking for resumable imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from e2n.enex import ExtractedNote


RUN_STATUS_ACTIVE = "active"
OPERATION_STATUS_PENDING = "pending"
OPERATION_STATUS_IN_PROGRESS = "in_progress"
OPERATION_STATUS_COMMITTED = "committed"
OPERATION_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class OperationRecord:
    """One queued write operation for the Notion import pipeline."""

    operation_id: int
    run_id: str
    note_id: str
    operation_type: str
    payload_json: str
    idempotency_key: str
    status: str
    attempt_count: int
    next_retry_at: str | None

    @property
    def payload(self) -> dict[str, Any]:
        """Decode the queued payload JSON object."""
        loaded = json.loads(self.payload_json)
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("operation payload must be a JSON object")


@dataclass(frozen=True)
class NoteRecord:
    """One extracted note row tracked in durable state."""

    note_id: str
    title: str
    tags_json: str
    content_hash: str
    status: str

    @property
    def tags(self) -> tuple[str, ...]:
        """Return note tags decoded from storage."""
        loaded = json.loads(self.tags_json)
        if isinstance(loaded, list):
            return tuple(str(item) for item in loaded)
        return ()


class ProcessingStateStore:
    """SQLite-backed run state for restart-safe import execution."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._initialize_schema()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection.close()

    def latest_run_id(self) -> str | None:
        """Return the most recent run id, if one exists."""
        row = self._connection.execute(
            """
            SELECT run_id
            FROM runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return str(row["run_id"])

    def run_exists(self, run_id: str) -> bool:
        """Return whether the run id exists in storage."""
        row = self._connection.execute(
            "SELECT 1 FROM runs WHERE run_id = ? LIMIT 1",
            (run_id,),
        ).fetchone()
        return row is not None

    def begin_run(self, source_path: Path, output_directory: Path, config: dict[str, Any] | None = None) -> str:
        """Create and return a run id for one extraction/import attempt."""
        timestamp = _utc_now().strftime("%Y%m%dT%H%M%S.%fZ")
        run_id = f"run-{timestamp}"
        config_json = json.dumps(config or {}, sort_keys=True)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO runs (run_id, source_path, output_directory, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    str(source_path),
                    str(output_directory),
                    config_json,
                    RUN_STATUS_ACTIVE,
                    _utc_now_iso(),
                    _utc_now_iso(),
                ),
            )
        return run_id

    def upsert_note(
        self,
        run_id: str,
        note: ExtractedNote,
        source_path: Path,
        status: str,
        error_message: str = "",
    ) -> None:
        """Insert or update one note status within a run."""
        tags_json = json.dumps(note.tags)
        reasons_json = json.dumps([str(reason) for reason in note.exception_reasons])
        content_hash = self.note_content_hash(note)
        now = _utc_now_iso()

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO notes (
                    run_id,
                    note_id,
                    title,
                    note_path,
                    source_path,
                    tags_json,
                    exception_reasons_json,
                    content_hash,
                    status,
                    error_message,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, note_id) DO UPDATE SET
                    title=excluded.title,
                    note_path=excluded.note_path,
                    source_path=excluded.source_path,
                    tags_json=excluded.tags_json,
                    exception_reasons_json=excluded.exception_reasons_json,
                    content_hash=excluded.content_hash,
                    status=excluded.status,
                    error_message=excluded.error_message,
                    updated_at=excluded.updated_at
                """,
                (
                    run_id,
                    note.note_id,
                    note.title,
                    str(note.path),
                    str(source_path),
                    tags_json,
                    reasons_json,
                    content_hash,
                    status,
                    error_message,
                    now,
                ),
            )

    def enqueue_operation(
        self,
        run_id: str,
        note_id: str,
        operation_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> int:
        """Add one queued operation, reusing an existing row for duplicate keys."""
        payload_json = json.dumps(payload, sort_keys=True)
        now = _utc_now_iso()

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO operations (
                    run_id,
                    note_id,
                    operation_type,
                    payload_json,
                    idempotency_key,
                    status,
                    attempt_count,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(run_id, idempotency_key) DO NOTHING
                """,
                (
                    run_id,
                    note_id,
                    operation_type,
                    payload_json,
                    idempotency_key,
                    OPERATION_STATUS_PENDING,
                    now,
                    now,
                ),
            )

            row = self._connection.execute(
                """
                SELECT operation_id
                FROM operations
                WHERE run_id = ? AND idempotency_key = ?
                """,
                (run_id, idempotency_key),
            ).fetchone()

        if row is None:
            raise RuntimeError("failed to enqueue operation")
        return int(row["operation_id"])

    def list_notes(self, run_id: str, status: str | None = None) -> list[NoteRecord]:
        """Return notes for one run, optionally filtered by status."""
        if status is None:
            rows = self._connection.execute(
                """
                SELECT note_id, title, tags_json, content_hash, status
                FROM notes
                WHERE run_id = ?
                ORDER BY note_id ASC
                """,
                (run_id,),
            ).fetchall()
        else:
            rows = self._connection.execute(
                """
                SELECT note_id, title, tags_json, content_hash, status
                FROM notes
                WHERE run_id = ? AND status = ?
                ORDER BY note_id ASC
                """,
                (run_id, status),
            ).fetchall()
        return [
            NoteRecord(
                note_id=str(row["note_id"]),
                title=str(row["title"]),
                tags_json=str(row["tags_json"]),
                content_hash=str(row["content_hash"]),
                status=str(row["status"]),
            )
            for row in rows
        ]

    def count_operations_by_status(self, run_id: str) -> dict[str, int]:
        """Return operation status counts for one run."""
        rows = self._connection.execute(
            """
            SELECT status, COUNT(*) AS total
            FROM operations
            WHERE run_id = ?
            GROUP BY status
            """,
            (run_id,),
        ).fetchall()
        return {str(row["status"]): int(row["total"]) for row in rows}

    def reset_run(self, run_id: str) -> int:
        """Reset all operations for one run to pending and clear checkpoints/maps."""
        with self._connection:
            self._connection.execute("DELETE FROM checkpoints WHERE run_id = ?", (run_id,))
            self._connection.execute("DELETE FROM notion_map WHERE run_id = ?", (run_id,))
            updated = self._connection.execute(
                """
                UPDATE operations
                SET status = ?,
                    attempt_count = 0,
                    next_retry_at = NULL,
                    last_error = NULL,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (OPERATION_STATUS_PENDING, _utc_now_iso(), run_id),
            )
        return int(updated.rowcount)

    def wipe_local_run(self, run_id: str) -> None:
        """Delete all local state for one run."""
        with self._connection:
            self._connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def list_notion_object_ids(self, run_id: str) -> list[str]:
        """Return mapped Notion object ids for one run."""
        rows = self._connection.execute(
            """
            SELECT notion_object_id
            FROM notion_map
            WHERE run_id = ? AND notion_object_id <> ''
            ORDER BY note_id ASC
            """,
            (run_id,),
        ).fetchall()
        return [str(row["notion_object_id"]) for row in rows]

    def clear_notion_map(self, run_id: str) -> int:
        """Delete Notion object mappings for one run."""
        with self._connection:
            deleted = self._connection.execute(
                "DELETE FROM notion_map WHERE run_id = ?",
                (run_id,),
            )
        return int(deleted.rowcount)

    def claim_next_operation(self, run_id: str, now: datetime | None = None) -> OperationRecord | None:
        """Claim the next due operation and mark it in progress."""
        now_dt = now or _utc_now()
        now_iso = _iso(now_dt)

        with self._connection:
            row = self._connection.execute(
                """
                SELECT operation_id
                FROM operations
                WHERE run_id = ?
                  AND status IN (?, ?)
                  AND (next_retry_at IS NULL OR next_retry_at <= ?)
                ORDER BY operation_id ASC
                LIMIT 1
                """,
                (run_id, OPERATION_STATUS_PENDING, OPERATION_STATUS_FAILED, now_iso),
            ).fetchone()
            if row is None:
                return None

            self._connection.execute(
                """
                UPDATE operations
                SET status = ?,
                    updated_at = ?
                WHERE operation_id = ?
                """,
                (OPERATION_STATUS_IN_PROGRESS, now_iso, int(row["operation_id"])),
            )

            selected = self._connection.execute(
                """
                SELECT
                    operation_id,
                    run_id,
                    note_id,
                    operation_type,
                    payload_json,
                    idempotency_key,
                    status,
                    attempt_count,
                    next_retry_at
                FROM operations
                WHERE operation_id = ?
                """,
                (int(row["operation_id"]),),
            ).fetchone()

        if selected is None:
            return None

        return OperationRecord(
            operation_id=int(selected["operation_id"]),
            run_id=str(selected["run_id"]),
            note_id=str(selected["note_id"]),
            operation_type=str(selected["operation_type"]),
            payload_json=str(selected["payload_json"]),
            idempotency_key=str(selected["idempotency_key"]),
            status=str(selected["status"]),
            attempt_count=int(selected["attempt_count"]),
            next_retry_at=str(selected["next_retry_at"]) if selected["next_retry_at"] is not None else None,
        )

    def mark_operation_committed(self, operation_id: int, notion_object_id: str = "") -> None:
        """Mark one operation as committed and record a checkpoint."""
        now = _utc_now_iso()
        with self._connection:
            row = self._connection.execute(
                "SELECT run_id, note_id FROM operations WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"operation_id not found: {operation_id}")

            self._connection.execute(
                """
                UPDATE operations
                SET status = ?,
                    last_error = NULL,
                    next_retry_at = NULL,
                    updated_at = ?
                WHERE operation_id = ?
                """,
                (OPERATION_STATUS_COMMITTED, now, operation_id),
            )

            self._connection.execute(
                """
                INSERT INTO checkpoints (run_id, last_committed_operation_id, committed_at)
                VALUES (?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    last_committed_operation_id = excluded.last_committed_operation_id,
                    committed_at = excluded.committed_at
                """,
                (str(row["run_id"]), operation_id, now),
            )

            if notion_object_id:
                self._connection.execute(
                    """
                    INSERT INTO notion_map (run_id, note_id, notion_object_id, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(run_id, note_id) DO UPDATE SET
                        notion_object_id = excluded.notion_object_id,
                        updated_at = excluded.updated_at
                    """,
                    (str(row["run_id"]), str(row["note_id"]), notion_object_id, now),
                )

    def mark_operation_failed(self, operation_id: int, error_message: str, retry_after_seconds: int = 0) -> None:
        """Mark one operation as failed and schedule the next retry."""
        now = _utc_now()
        if retry_after_seconds > 0:
            next_retry = _iso(now + timedelta(seconds=retry_after_seconds))
        else:
            next_retry = _iso(now)

        with self._connection:
            self._connection.execute(
                """
                UPDATE operations
                SET status = ?,
                    attempt_count = attempt_count + 1,
                    last_error = ?,
                    next_retry_at = ?,
                    updated_at = ?
                WHERE operation_id = ?
                """,
                (OPERATION_STATUS_FAILED, error_message, next_retry, _iso(now), operation_id),
            )

    def note_content_hash(self, note: ExtractedNote) -> str:
        """Return a deterministic note fingerprint for idempotency decisions."""
        payload = {
            "note_id": note.note_id,
            "title": note.title,
            "path": str(note.path),
            "tags": list(note.tags),
            "reasons": [str(reason) for reason in note.exception_reasons],
        }
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    output_directory TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notes (
                    run_id TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    note_path TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    exception_reasons_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_message TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, note_id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS operations (
                    operation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    notion_object_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (run_id, idempotency_key),
                    FOREIGN KEY (run_id, note_id) REFERENCES notes(run_id, note_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY,
                    last_committed_operation_id INTEGER NOT NULL,
                    committed_at TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS notion_map (
                    run_id TEXT NOT NULL,
                    note_id TEXT NOT NULL,
                    notion_object_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (run_id, note_id),
                    FOREIGN KEY (run_id, note_id) REFERENCES notes(run_id, note_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_notes_status ON notes(run_id, status);
                CREATE INDEX IF NOT EXISTS idx_operations_ready
                    ON operations(run_id, status, next_retry_at, operation_id);
                """
            )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _utc_now_iso() -> str:
    return _iso(_utc_now())
