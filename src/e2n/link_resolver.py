"""Resolve imported Evernote link placeholders after all notes are imported."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from e2n.exceptions import ExceptionReason
from e2n.notion import NotionClient, NotionPageRef


@dataclass(frozen=True)
class EvernoteLinkException:
    """An exception row seed for an unresolved Evernote embedded link."""

    note_id: str
    note_title: str
    reasons: tuple[str, ...]
    source_path: str
    block_url: str
    link_text: str
    link_value: str


@dataclass(frozen=True)
class LinkResolutionResult:
    """Result of attempting to resolve one Evernote embedded link."""

    exception: EvernoteLinkException
    matched_page: NotionPageRef | None
    updated: bool


def resolve_evernote_links(exception_file: Path, notion_key: str, client: NotionClient | None = None) -> list[LinkResolutionResult]:
    """Resolve Evernote link warning placeholders using exact Notion title matches."""
    notion = client or NotionClient(notion_key)
    results: list[LinkResolutionResult] = []
    for exception in read_evernote_link_exceptions(exception_file):
        matched_page = find_page_by_title(notion, exception.link_text)
        updated = False
        block_id = block_id_from_url(exception.block_url)
        if matched_page and matched_page.url and block_id:
            notion.update_block_with_page_link(block_id, exception.link_text, matched_page.url)
            updated = True
        results.append(LinkResolutionResult(exception=exception, matched_page=matched_page, updated=updated))
    return results


def read_evernote_link_exceptions(exception_file: Path) -> tuple[EvernoteLinkException, ...]:
    """Read Evernote-link exception rows from an extraction ``exceptions.txt`` file."""
    records: list[EvernoteLinkException] = []
    for line in exception_file.expanduser().read_text(encoding="utf-8").splitlines():
        note_id, title, reasons, source_path, block_url, link_text, link_value = _split_exception_record(line)
        reason_values = tuple(reason for reason in reasons.split(",") if reason)
        if str(ExceptionReason.EVERNOTE_LINK) in reason_values:
            records.append(
                EvernoteLinkException(
                    note_id=note_id,
                    note_title=title,
                    reasons=reason_values,
                    source_path=source_path,
                    block_url=block_url,
                    link_text=link_text,
                    link_value=link_value,
                )
            )
    return tuple(records)


def find_page_by_title(client: NotionClient, title: str) -> NotionPageRef | None:
    """Find a visible Notion page with a title matching the Evernote link text."""
    normalized_title = _normalize_title(title)
    matches = [page for page in client.search_pages(title) if _normalize_title(page.title) == normalized_title]
    return matches[0] if len(matches) == 1 else None


def block_id_from_url(block_url: str) -> str:
    """Extract a Notion block ID from a block URL fragment."""
    if "#" not in block_url:
        return ""
    fragment = unquote(block_url.rsplit("#", 1)[1])
    return fragment.replace("-", "")


def _split_exception_record(line: str) -> tuple[str, str, str, str, str, str, str]:
    fields = line.split("\t")
    return tuple(fields + [""] * (7 - len(fields)))[:7]  # type: ignore[return-value]


def _normalize_title(title: str) -> str:
    return " ".join(title.casefold().split())
