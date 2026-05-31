"""Notion API helpers for migration workspace setup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from e2n.exceptions import EvernoteEmbeddedLinkRecord, UnsupportedContentRecord


DEFAULT_CONVERTED_PAGE_TITLE = "Evernote Import"
DEFAULT_EXCEPTIONS_PAGE_TITLE = "Evernote Import Exceptions"
DEFAULT_EXCEPTIONS_DATABASE_TITLE = "Import-Exceptions"
EXCEPTION_REASON_PROPERTY = "Reason"
IMPORT_TAGS_PROPERTY = "Tags"

JsonObject = dict[str, Any]


class NotionAPIError(RuntimeError):
    """Raised when Notion rejects an API request."""


@dataclass(frozen=True)
class NotionPageRef:
    """Minimal page metadata needed by the migration bootstrap."""

    page_id: str
    title: str
    url: str | None
    parent_page_id: str | None
    parent_type: str = ""


@dataclass(frozen=True)
class NotionBootstrapResult:
    """Pages created or reused for one migration workspace."""

    root: NotionPageRef
    converted: NotionPageRef
    exceptions: NotionPageRef


@dataclass(frozen=True)
class NotionDatabaseRef:
    """Minimal database metadata needed for idempotent import setup."""

    database_id: str
    title: str
    url: str | None
    parent_page_id: str | None


class NotionClient:
    """Migration-focused wrapper around the Notion Python SDK."""

    def __init__(self, notion_key: str, sdk_client: Any | None = None) -> None:
        if sdk_client is None:
            try:
                from notion_client import Client
            except ImportError as exc:
                raise NotionAPIError("Install notion-client to use Notion API features") from exc
            sdk_client = Client(auth=notion_key)
        self._sdk_client = sdk_client

    def search_pages(self, query: str | None = None) -> list[NotionPageRef]:
        """Return pages shared with the integration, optionally filtered by title."""
        pages: list[NotionPageRef] = []
        start_cursor: str | None = None

        while True:
            body: JsonObject = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100,
            }
            if query:
                body["query"] = query
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = self._sdk_call(self._sdk_client.search, **body)
            pages.extend(_page_ref(page) for page in response.get("results", []))
            if not response.get("has_more"):
                return pages
            start_cursor = response.get("next_cursor")

    def search_databases(self, query: str | None = None) -> list[NotionDatabaseRef]:
        """Return databases shared with the integration, optionally filtered by title."""
        databases: list[NotionDatabaseRef] = []
        start_cursor: str | None = None

        while True:
            body: JsonObject = {
                "filter": {"property": "object", "value": "database"},
                "page_size": 100,
            }
            if query:
                body["query"] = query
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = self._sdk_call(self._sdk_client.search, **body)
            databases.extend(_database_ref(database) for database in response.get("results", []))
            if not response.get("has_more"):
                return databases
            start_cursor = response.get("next_cursor")

    def create_page(self, parent_page_id: str, title: str) -> NotionPageRef:
        """Create a new child page under an existing Notion page."""
        body = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "properties": {"title": [{"text": {"content": title}}]},
        }
        return _page_ref(self._sdk_call(self._sdk_client.pages.create, **body))

    def create_workspace_page(self, title: str) -> NotionPageRef:
        """Create a top-level workspace page when the integration type allows it."""
        body = {
            "parent": {"type": "workspace", "workspace": True},
            "properties": {"title": [{"text": {"content": title}}]},
        }
        return _page_ref(self._sdk_call(self._sdk_client.pages.create, **body))

    def create_database(self, parent_page_id: str, title: str, properties: JsonObject) -> NotionDatabaseRef:
        """Create a child database under a Notion page."""
        body = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": title}}],
            "properties": properties,
        }
        return _database_ref(self._sdk_call(self._sdk_client.databases.create, **body))

    def create_database_row(self, database_id: str, title: str, tags: tuple[str, ...] | list[str]) -> NotionPageRef:
        """Create one page row in an import database."""
        body = {
            "parent": {"database_id": database_id},
            "properties": {
                "Name": {"title": [{"text": {"content": title}}]},
                IMPORT_TAGS_PROPERTY: import_tags_property(tags),
            },
        }
        return _page_ref(self._sdk_call(self._sdk_client.pages.create, **body))

    def archive_page(self, page_id: str) -> NotionPageRef:
        """Archive one Notion page by id for cleanup workflows."""
        return _page_ref(self._sdk_call(self._sdk_client.pages.update, page_id=page_id, archived=True))

    def update_block_with_page_link(self, block_id: str, link_text: str, page_url: str) -> JsonObject:
        """Replace a warning placeholder block with a paragraph containing an inline page link."""
        body = {
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {
                            "content": link_text,
                            "link": {"url": page_url},
                        },
                    }
                ]
            }
        }
        return self._sdk_call(self._sdk_client.blocks.update, block_id=block_id, **body)

    def _sdk_call(self, sdk_method: Any, **kwargs: Any) -> JsonObject:
        try:
            return sdk_method(**kwargs)
        except Exception as exc:
            raise NotionAPIError(f"Notion SDK request failed: {exc}") from exc


def multi_select_property(values: tuple[str, ...] | list[str]) -> JsonObject:
    """Build a Notion multi-select property value from unique non-empty values."""
    unique_values = tuple(dict.fromkeys(value.strip() for value in values if value.strip()))
    return {"multi_select": [{"name": value} for value in unique_values]}


def exception_reason_property(reasons: tuple[str, ...] | list[str]) -> JsonObject:
    """Build the exception database Reason multi-select property."""
    return multi_select_property(reasons)


def import_tags_property(tags: tuple[str, ...] | list[str]) -> JsonObject:
    """Build the imported note database Tags multi-select property."""
    return multi_select_property(tags)


def import_database_properties() -> JsonObject:
    """Return the schema for one imported ENEX database."""
    return {
        "Name": {"title": {}},
        IMPORT_TAGS_PROPERTY: {"multi_select": {}},
    }


def exception_database_properties() -> JsonObject:
    """Return the schema for the Import-Exceptions database."""
    return {
        "Note Name": {"title": {}},
        "Link": {"url": {}},
        EXCEPTION_REASON_PROPERTY: {"multi_select": {}},
        "Error Message": {"rich_text": {}},
        "Source File": {"rich_text": {}},
        "Linkable Text": {"rich_text": {}},
        "Evernote Attribute": {"rich_text": {}},
        "Notion Target": {"rich_text": {}},
        "External Resource": {"rich_text": {}},
    }


def unsupported_content_marker_block(record: UnsupportedContentRecord) -> JsonObject:
    """Build a visible Notion block for content that could not be imported."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": record.marker_text}}],
            "icon": {"type": "emoji", "emoji": "!"},
            "color": "yellow_background",
        },
    }


def evernote_embedded_link_marker_block(record: EvernoteEmbeddedLinkRecord) -> JsonObject:
    """Build a visible warning block for an unresolved Evernote embedded link."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": record.marker_text}}],
            "icon": {"type": "emoji", "emoji": "⚠️"},
            "color": "yellow_background",
        },
    }


def bootstrap_notion_pages(
    notion_key: str,
    root_title: str | None = None,
    converted_title: str = DEFAULT_CONVERTED_PAGE_TITLE,
    exceptions_title: str = DEFAULT_EXCEPTIONS_PAGE_TITLE,
    *,
    client: NotionClient | None = None,
) -> NotionBootstrapResult:
    """Create or reuse the Notion pages required for migration output.

    When ``root_title`` is provided, the function uses the matching shared page as
    the parent. Without it, the function creates or reuses top-level workspace
    pages for the migration.
    """
    if not notion_key.strip():
        raise ValueError("notion_key is required")

    notion = client or NotionClient(notion_key)
    if root_title is None:
        all_visible_pages = notion.search_pages()
        workspace = NotionPageRef(
            page_id="",
            title="Workspace",
            url=None,
            parent_page_id=None,
            parent_type="workspace",
        )
        converted = _find_workspace_page(all_visible_pages, converted_title)
        if converted is None:
            converted = notion.create_workspace_page(converted_title)

        exceptions = _find_workspace_page(all_visible_pages, exceptions_title)
        if exceptions is None:
            exceptions = notion.create_workspace_page(exceptions_title)

        return NotionBootstrapResult(root=workspace, converted=converted, exceptions=exceptions)

    shared_pages = notion.search_pages(root_title)
    root = _select_root_page(shared_pages, root_title)
    all_visible_pages = notion.search_pages()

    converted = _find_child_page(all_visible_pages, root.page_id, converted_title)
    if converted is None:
        converted = notion.create_page(root.page_id, converted_title)

    exceptions = _find_child_page(all_visible_pages, root.page_id, exceptions_title)
    if exceptions is None:
        exceptions = notion.create_page(root.page_id, exceptions_title)

    return NotionBootstrapResult(root=root, converted=converted, exceptions=exceptions)


def ensure_import_database(client: NotionClient, parent_page_id: str, database_title: str) -> NotionDatabaseRef:
    """Create or reuse the import database for one ENEX file under Evernote Import."""
    return ensure_child_database(client, parent_page_id, database_title, import_database_properties())


def ensure_exception_database(client: NotionClient, parent_page_id: str) -> NotionDatabaseRef:
    """Create or reuse the single Import-Exceptions database."""
    return ensure_child_database(
        client,
        parent_page_id,
        DEFAULT_EXCEPTIONS_DATABASE_TITLE,
        exception_database_properties(),
    )


def ensure_child_database(
    client: NotionClient,
    parent_page_id: str,
    database_title: str,
    properties: JsonObject,
) -> NotionDatabaseRef:
    """Create a child database only when an exact existing sibling is absent."""
    existing = _find_child_database(client.search_databases(database_title), parent_page_id, database_title)
    if existing is not None:
        return existing
    return client.create_database(parent_page_id, database_title, properties)


def _select_root_page(pages: list[NotionPageRef], root_title: str | None) -> NotionPageRef:
    if root_title is not None:
        matches = [page for page in pages if page.title == root_title]
        if not matches:
            raise ValueError(f"Could not find a shared Notion page titled {root_title!r}")
        return _deepest_page(matches)

    raise ValueError("root_title is required when selecting a parent page")


def _deepest_page(pages: list[NotionPageRef]) -> NotionPageRef:
    by_id = {page.page_id: page for page in pages}

    def depth(page: NotionPageRef) -> int:
        seen: set[str] = set()
        current = page
        distance = 0
        while current.parent_page_id and current.parent_page_id in by_id and current.parent_page_id not in seen:
            seen.add(current.page_id)
            current = by_id[current.parent_page_id]
            distance += 1
        return distance

    return max(pages, key=lambda page: (depth(page), page.title.lower(), page.page_id))


def _find_child_page(pages: list[NotionPageRef], parent_page_id: str, title: str) -> NotionPageRef | None:
    matches = [page for page in pages if page.parent_page_id == parent_page_id and page.title == title]
    return matches[0] if matches else None


def _find_workspace_page(pages: list[NotionPageRef], title: str) -> NotionPageRef | None:
    matches = [page for page in pages if page.parent_type == "workspace" and page.title == title]
    return matches[0] if matches else None


def _find_child_database(
    databases: list[NotionDatabaseRef],
    parent_page_id: str,
    title: str,
) -> NotionDatabaseRef | None:
    matches = [database for database in databases if database.parent_page_id == parent_page_id and database.title == title]
    return matches[0] if matches else None


def _page_ref(page: JsonObject) -> NotionPageRef:
    parent = page.get("parent", {})
    parent_page_id = parent.get("page_id") if parent.get("type") == "page_id" else None
    return NotionPageRef(
        page_id=page["id"],
        title=_page_title(page),
        url=page.get("url"),
        parent_page_id=parent_page_id,
        parent_type=parent.get("type", ""),
    )


def _database_ref(database: JsonObject) -> NotionDatabaseRef:
    parent = database.get("parent", {})
    parent_page_id = parent.get("page_id") if parent.get("type") == "page_id" else None
    return NotionDatabaseRef(
        database_id=database["id"],
        title=_title_text(database.get("title", [])),
        url=database.get("url"),
        parent_page_id=parent_page_id,
    )


def _page_title(page: JsonObject) -> str:
    properties = page.get("properties", {})
    for value in properties.values():
        if value.get("type") == "title":
            return "".join(part.get("plain_text", "") for part in value.get("title", [])).strip()
    return ""


def _title_text(title_items: list[JsonObject]) -> str:
    return "".join(part.get("plain_text", "") for part in title_items).strip()
