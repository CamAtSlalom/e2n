"""Rebuild exception and review projections from durable extraction artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from e2n.enex import discover_enex_sources
from e2n.notion import (
    EXCEPTION_KEY_PROPERTY,
    EXCEPTION_REASON_PROPERTY,
    EXCEPTION_STATUS_PROPERTY,
    NotionClient,
    bootstrap_notion_pages,
    ensure_exception_database,
    exception_reason_property,
)
from e2n.state import ProcessingStateStore


REVIEW_PASSED = "review_passed"
REVIEW_PASSED_WITH_OPEN_EXCEPTIONS = "review_passed_with_open_exceptions"
REVIEW_FAILED = "review_failed"

UNSUPPORTED_MARKER_PREFIX = "Unsupported content could not be imported automatically:"
EVERNOTE_LINK_MARKER_PREFIX = "Evernote link requires manual resolution:"


@dataclass(frozen=True)
class RebuildExceptionRecord:
    """One normalized exception record rebuilt from extraction artifacts."""

    exception_id: str
    note_id: str
    note_title: str
    source_file: str
    source_path: str
    exception_type: str
    reason: str
    severity: str
    notion_target_type: str
    notion_target_id: str
    error_message: str
    external_resource_ref: str
    status: str
    link_text: str
    link_value: str
    block_url: str


@dataclass(frozen=True)
class RebuildSummary:
    """Summary counts for one rebuild execution."""

    run_id: str
    source_file: str
    total_notes: int
    total_exceptions: int
    review_passed: int
    review_passed_with_open_exceptions: int
    review_failed: int


def rebuild_exceptions_for_source(
    source_path: Path,
    processing_directory: Path,
    *,
    apply: bool,
    review_version: str,
    from_notion: bool = False,
    notion: NotionClient | None = None,
    sync_notion_exceptions: bool = False,
    exception_database_id: str = "",
) -> RebuildSummary:
    """Rebuild SQL exception and review projections for one ENEX source file.

    The rebuild is deterministic from extraction outputs:
    - `state.db` for notes/run information
    - `exceptions.txt` for extracted exception seeds
    """
    output_dir = processing_directory.expanduser().resolve() / source_path.stem
    state_path = output_dir / "state.db"
    exceptions_path = output_dir / "exceptions.txt"

    if not state_path.exists():
        raise FileNotFoundError(f"No state.db found for source: {source_path}. Run --converting first.")

    state = ProcessingStateStore(state_path)
    try:
        run_id = state.latest_run_id()
        if run_id is None:
            raise ValueError(f"No recorded run in {state_path}. Run --converting first.")

        notes = state.list_notes(run_id)
        note_ids = {note.note_id for note in notes}
        if from_notion:
            if notion is None:
                raise ValueError("Notion client is required when from_notion=True")
            rebuilt = _read_exception_records_from_notion(
                notion,
                run_id=run_id,
                source_file=source_path.name,
                source_path=str(source_path),
                note_title_by_id={note.note_id: note.title for note in notes},
                notion_mappings=state.list_notion_mappings(run_id),
            )
        else:
            rebuilt = _read_exception_records(exceptions_path, run_id=run_id, source_file=source_path.name)

        exception_note_ids = {record.note_id for record in rebuilt}
        review_rows = []
        for note in notes:
            if note.note_id in exception_note_ids:
                review_rows.append((note.note_id, REVIEW_PASSED_WITH_OPEN_EXCEPTIONS, "open exceptions present"))
            else:
                review_rows.append((note.note_id, REVIEW_PASSED, ""))

        # Any exception rows referencing a missing note id are tracked as review_failed
        missing_note_exception_count = 0
        if rebuilt:
            for record in rebuilt:
                if record.note_id not in note_ids:
                    missing_note_exception_count += 1

        if apply:
            state.reset_exception_projection(run_id)
            for record in rebuilt:
                state.upsert_exception_projection(run_id=run_id, record=record)

            state.reset_note_reviews(run_id)
            for note_id, review_result, review_diff in review_rows:
                state.upsert_note_review(
                    run_id=run_id,
                    note_id=note_id,
                    review_version=review_version,
                    review_result=review_result,
                    review_diff=review_diff,
                )

            if missing_note_exception_count:
                # Create one synthetic failed review marker for data integrity drift.
                state.upsert_note_review(
                    run_id=run_id,
                    note_id="__exception_integrity__",
                    review_version=review_version,
                    review_result=REVIEW_FAILED,
                    review_diff=f"{missing_note_exception_count} exception rows reference unknown note ids",
                )

            if sync_notion_exceptions and notion is not None and exception_database_id:
                _sync_notion_exception_rows(
                    notion,
                    exception_database_id=exception_database_id,
                    source_file=source_path.name,
                    rebuilt=rebuilt,
                )

        review_passed = sum(1 for _, result, _ in review_rows if result == REVIEW_PASSED)
        review_with_exceptions = sum(
            1 for _, result, _ in review_rows if result == REVIEW_PASSED_WITH_OPEN_EXCEPTIONS
        )
        review_failed = 1 if missing_note_exception_count else 0

        return RebuildSummary(
            run_id=run_id,
            source_file=source_path.name,
            total_notes=len(notes),
            total_exceptions=len(rebuilt),
            review_passed=review_passed,
            review_passed_with_open_exceptions=review_with_exceptions,
            review_failed=review_failed,
        )
    finally:
        state.close()


def rebuild_exceptions_for_sources(
    enex_source: Path,
    processing_directory: Path,
    *,
    apply: bool,
    review_version: str,
    from_notion: bool = False,
    notion_key: str = "",
    notion_root: str | None = None,
    sync_notion_exceptions: bool = False,
) -> list[RebuildSummary]:
    """Rebuild projections for one source file or all files in a source directory."""
    notion: NotionClient | None = None
    exception_database_id = ""
    if from_notion or sync_notion_exceptions:
        if not notion_key.strip():
            raise ValueError("Notion key is required for Notion-backed rebuild options")
        notion = NotionClient(notion_key)
    if sync_notion_exceptions:
        if notion is None:
            raise ValueError("Notion client unavailable for sync")
        bootstrap = bootstrap_notion_pages(notion_key, root_title=notion_root, client=notion)
        exception_database = ensure_exception_database(notion, bootstrap.exceptions.page_id)
        exception_database_id = exception_database.database_id

    summaries: list[RebuildSummary] = []
    for source in discover_enex_sources(enex_source):
        summaries.append(
            rebuild_exceptions_for_source(
                source,
                processing_directory,
                apply=apply,
                review_version=review_version,
                from_notion=from_notion,
                notion=notion,
                sync_notion_exceptions=sync_notion_exceptions,
                exception_database_id=exception_database_id,
            )
        )
    return summaries


def _read_exception_records(exceptions_path: Path, *, run_id: str, source_file: str) -> tuple[RebuildExceptionRecord, ...]:
    if not exceptions_path.exists():
        return ()

    records: list[RebuildExceptionRecord] = []
    for line in exceptions_path.read_text(encoding="utf-8").splitlines():
        note_id, title, reasons, source_path, block_url, link_text, link_value = _split_exception_record(line)
        for reason in [value.strip() for value in reasons.split(",") if value.strip()]:
            exception_type = _exception_type(reason)
            record = RebuildExceptionRecord(
                exception_id=_exception_id(run_id, note_id, reason, block_url, link_value),
                note_id=note_id,
                note_title=title,
                source_file=source_file,
                source_path=source_path,
                exception_type=exception_type,
                reason=reason,
                severity=_severity(reason),
                notion_target_type="block" if block_url else "page",
                notion_target_id=block_url,
                error_message=_default_error_message(reason, link_text, link_value),
                external_resource_ref="",
                status="open",
                link_text=link_text,
                link_value=link_value,
                block_url=block_url,
            )
            records.append(record)

    return tuple(records)


def _split_exception_record(line: str) -> tuple[str, str, str, str, str, str, str]:
    fields = line.split("\t")
    padded = tuple(fields + [""] * (7 - len(fields)))
    return padded[:7]  # type: ignore[return-value]


def _exception_id(run_id: str, note_id: str, reason: str, block_url: str, link_value: str) -> str:
    payload = "|".join([run_id, note_id, reason, block_url, link_value])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _exception_type(reason: str) -> str:
    mapping = {
        "Empty Title": "title",
        "No Content": "content",
        "Unsupported Content": "content",
        "Evernote Link": "link",
    }
    return mapping.get(reason, "attribute")


def _severity(reason: str) -> str:
    mapping = {
        "Empty Title": "low",
        "No Content": "medium",
        "Unsupported Content": "high",
        "Evernote Link": "medium",
    }
    return mapping.get(reason, "medium")


def _default_error_message(reason: str, link_text: str, link_value: str) -> str:
    if reason == "Evernote Link":
        return f"Embedded Evernote link requires resolution: {link_text or link_value}"
    if reason == "No Content":
        return "Note has no content and no resources"
    if reason == "Empty Title":
        return "Note title was empty; defaulted to Empty Title"
    if reason == "Unsupported Content":
        return "Unsupported content requires manual remediation"
    return f"Manual remediation required: {reason}"


def _read_exception_records_from_notion(
    notion: NotionClient,
    *,
    run_id: str,
    source_file: str,
    source_path: str,
    note_title_by_id: dict[str, str],
    notion_mappings: list,
) -> tuple[RebuildExceptionRecord, ...]:
    records: list[RebuildExceptionRecord] = []
    for mapping in notion_mappings:
        note_id = mapping.note_id
        note_title = note_title_by_id.get(note_id, "")
        for block in _walk_blocks_recursive(notion, mapping.notion_object_id):
            block_id = str(block.get("id", ""))
            marker_text = _callout_text(block)
            if not marker_text:
                continue

            if marker_text.startswith(EVERNOTE_LINK_MARKER_PREFIX):
                link_text = marker_text.removeprefix(EVERNOTE_LINK_MARKER_PREFIX).strip()
                reason = "Evernote Link"
                records.append(
                    RebuildExceptionRecord(
                        exception_id=_exception_id(run_id, note_id, reason, block_id, link_text),
                        note_id=note_id,
                        note_title=note_title,
                        source_file=source_file,
                        source_path=source_path,
                        exception_type=_exception_type(reason),
                        reason=reason,
                        severity=_severity(reason),
                        notion_target_type="block",
                        notion_target_id=block_id,
                        error_message=_default_error_message(reason, link_text, ""),
                        external_resource_ref="",
                        status="open",
                        link_text=link_text,
                        link_value="",
                        block_url=block_id,
                    )
                )
            elif marker_text.startswith(UNSUPPORTED_MARKER_PREFIX):
                reason = "Unsupported Content"
                message = marker_text.removeprefix(UNSUPPORTED_MARKER_PREFIX).strip()
                records.append(
                    RebuildExceptionRecord(
                        exception_id=_exception_id(run_id, note_id, reason, block_id, message),
                        note_id=note_id,
                        note_title=note_title,
                        source_file=source_file,
                        source_path=source_path,
                        exception_type=_exception_type(reason),
                        reason=reason,
                        severity=_severity(reason),
                        notion_target_type="block",
                        notion_target_id=block_id,
                        error_message=_default_error_message(reason, "", ""),
                        external_resource_ref="",
                        status="open",
                        link_text="",
                        link_value="",
                        block_url=block_id,
                    )
                )

    return tuple(records)


def _walk_blocks_recursive(notion: NotionClient, block_id: str) -> tuple[dict, ...]:
    discovered: list[dict] = []
    for child in notion.list_block_children(block_id):
        discovered.append(child)
        if child.get("has_children"):
            discovered.extend(_walk_blocks_recursive(notion, str(child.get("id", ""))))
    return tuple(discovered)


def _callout_text(block: dict) -> str:
    if block.get("type") != "callout":
        return ""
    callout = block.get("callout", {})
    rich_text = callout.get("rich_text", [])
    chunks: list[str] = []
    for item in rich_text:
        if not isinstance(item, dict):
            continue
        text = item.get("plain_text")
        if isinstance(text, str):
            chunks.append(text)
            continue
        text_obj = item.get("text", {})
        if isinstance(text_obj, dict):
            content = text_obj.get("content")
            if isinstance(content, str):
                chunks.append(content)
    return "".join(chunks).strip()


def _sync_notion_exception_rows(
    notion: NotionClient,
    *,
    exception_database_id: str,
    source_file: str,
    rebuilt: tuple[RebuildExceptionRecord, ...],
) -> None:
    by_key = {record.exception_id: record for record in rebuilt}
    existing = _existing_exception_rows(notion, exception_database_id=exception_database_id, source_file=source_file)

    for exception_key, record in by_key.items():
        properties = _exception_row_properties(record, status="Open")
        existing_page_id = existing.get(exception_key)
        if existing_page_id:
            notion.update_page_properties(existing_page_id, properties)
        else:
            notion.create_database_page(exception_database_id, properties)

    rebuilt_keys = set(by_key)
    for exception_key, page_id in existing.items():
        if exception_key not in rebuilt_keys:
            notion.update_page_properties(page_id, {EXCEPTION_STATUS_PROPERTY: {"select": {"name": "Closed"}}})


def _existing_exception_rows(
    notion: NotionClient,
    *,
    exception_database_id: str,
    source_file: str,
) -> dict[str, str]:
    rows: dict[str, str] = {}
    for page in notion.search_pages():
        if page.parent_database_id != exception_database_id:
            continue
        payload = notion.retrieve_page_raw(page.page_id)
        props = payload.get("properties", {})
        file_name = _rich_text_property(props.get("Source File", {}))
        if file_name != source_file:
            continue
        exception_key = _rich_text_property(props.get(EXCEPTION_KEY_PROPERTY, {}))
        if exception_key:
            rows[exception_key] = page.page_id
    return rows


def _exception_row_properties(record: RebuildExceptionRecord, *, status: str) -> dict:
    return {
        "Note Name": {"title": [{"text": {"content": record.note_title or "Empty Title"}}]},
        EXCEPTION_KEY_PROPERTY: {"rich_text": [{"text": {"content": record.exception_id}}]},
        EXCEPTION_STATUS_PROPERTY: {"select": {"name": status}},
        "Link": {"url": record.block_url or None},
        EXCEPTION_REASON_PROPERTY: exception_reason_property([record.reason]),
        "Error Message": {"rich_text": [{"text": {"content": record.error_message}}]},
        "Source File": {"rich_text": [{"text": {"content": record.source_file}}]},
        "Linkable Text": {"rich_text": [{"text": {"content": record.link_text or record.link_value}}]},
        "Evernote Attribute": {"rich_text": [{"text": {"content": ""}}]},
        "Notion Target": {"rich_text": [{"text": {"content": record.notion_target_id}}]},
        "External Resource": {"rich_text": [{"text": {"content": record.external_resource_ref}}]},
    }


def _rich_text_property(property_value: dict) -> str:
    values = property_value.get("rich_text", [])
    chunks: list[str] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        plain = item.get("plain_text")
        if isinstance(plain, str):
            chunks.append(plain)
            continue
        text_obj = item.get("text", {})
        if isinstance(text_obj, dict):
            content = text_obj.get("content")
            if isinstance(content, str):
                chunks.append(content)
    return "".join(chunks).strip()
