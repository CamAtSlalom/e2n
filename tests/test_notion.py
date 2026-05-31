from e2n.cli import main
from e2n.exceptions import EvernoteEmbeddedLinkRecord, UnsupportedContentRecord
from e2n.notion import (
    DEFAULT_EXCEPTIONS_DATABASE_TITLE,
    NotionClient,
    NotionDatabaseRef,
    NotionPageRef,
    bootstrap_notion_pages,
    evernote_embedded_link_marker_block,
    ensure_exception_database,
    ensure_import_database,
    exception_reason_property,
    import_tags_property,
    unsupported_content_marker_block,
)


class FakeNotionClient:
    def __init__(self, pages: list[NotionPageRef], databases: list[NotionDatabaseRef] | None = None) -> None:
        self.pages = pages
        self.databases = databases or []
        self.created: list[tuple[str, str]] = []
        self.created_databases: list[tuple[str, str]] = []

    def search_pages(self, query: str | None = None) -> list[NotionPageRef]:
        if query is None:
            return list(self.pages)
        return [page for page in self.pages if query in page.title]

    def search_databases(self, query: str | None = None) -> list[NotionDatabaseRef]:
        if query is None:
            return list(self.databases)
        return [database for database in self.databases if query in database.title]

    def create_page(self, parent_page_id: str, title: str) -> NotionPageRef:
        page = NotionPageRef(
            page_id=f"created-{len(self.created) + 1}",
            title=title,
            url=None,
            parent_page_id=parent_page_id,
        )
        self.created.append((parent_page_id, title))
        self.pages.append(page)
        return page

    def create_workspace_page(self, title: str) -> NotionPageRef:
        page = NotionPageRef(
            page_id=f"workspace-created-{len(self.created) + 1}",
            title=title,
            url=None,
            parent_page_id=None,
            parent_type="workspace",
        )
        self.created.append(("workspace", title))
        self.pages.append(page)
        return page

    def create_database(self, parent_page_id: str, title: str, properties: dict) -> NotionDatabaseRef:
        database = NotionDatabaseRef(
            database_id=f"database-created-{len(self.created_databases) + 1}",
            title=title,
            url=None,
            parent_page_id=parent_page_id,
        )
        self.created_databases.append((parent_page_id, title))
        self.databases.append(database)
        return database


class FakePagesEndpoint:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.updated: list[dict] = []

    def create(self, **kwargs):
        self.created.append(kwargs)
        if "title" in kwargs["properties"]:
            title_text = kwargs["properties"]["title"][0]["text"]["content"]
        else:
            title_text = kwargs["properties"]["Name"]["title"][0]["text"]["content"]
        return {
            "id": "created",
            "url": "https://notion.so/created",
            "parent": kwargs["parent"],
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": title_text}],
                }
            },
        }

    def update(self, **kwargs):
        self.updated.append(kwargs)
        return {
            "id": kwargs["page_id"],
            "url": f"https://notion.so/{kwargs['page_id']}",
            "parent": {"type": "page_id", "page_id": "root"},
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": "Archived"}],
                }
            },
        }


class FakeSDKClient:
    def __init__(self) -> None:
        self.searches: list[dict] = []
        self.pages = FakePagesEndpoint()

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return {
            "results": [
                {
                    "id": "root",
                    "url": "https://notion.so/root",
                    "parent": {"type": "workspace", "workspace": True},
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"plain_text": "Root"}],
                        }
                    },
                }
            ],
            "has_more": False,
        }


def test_notion_client_uses_sdk_for_search_and_page_creation() -> None:
    sdk_client = FakeSDKClient()
    notion = NotionClient("notion-key", sdk_client=sdk_client)

    pages = notion.search_pages("Root")
    created = notion.create_page("root", "Evernote Import")

    assert pages == [
        NotionPageRef(
            page_id="root",
            title="Root",
            url="https://notion.so/root",
            parent_page_id=None,
            parent_type="workspace",
        )
    ]
    assert sdk_client.searches == [
        {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
            "query": "Root",
        }
    ]
    assert created == NotionPageRef(
        page_id="created",
        title="Evernote Import",
        url="https://notion.so/created",
        parent_page_id="root",
        parent_type="page_id",
    )
    assert sdk_client.pages.created == [
        {
            "parent": {"type": "page_id", "page_id": "root"},
            "properties": {"title": [{"text": {"content": "Evernote Import"}}]},
        }
    ]


def test_notion_client_can_create_workspace_page() -> None:
    sdk_client = FakeSDKClient()
    notion = NotionClient("notion-key", sdk_client=sdk_client)

    created = notion.create_workspace_page("Evernote Import")

    assert created == NotionPageRef(
        page_id="created",
        title="Evernote Import",
        url="https://notion.so/created",
        parent_page_id=None,
        parent_type="workspace",
    )
    assert sdk_client.pages.created == [
        {
            "parent": {"type": "workspace", "workspace": True},
            "properties": {"title": [{"text": {"content": "Evernote Import"}}]},
        }
    ]


def test_notion_client_can_create_database_row() -> None:
    sdk_client = FakeSDKClient()
    notion = NotionClient("notion-key", sdk_client=sdk_client)

    page = notion.create_database_row("database-1", "Imported Note", ["Project", "Archive"])

    assert page.page_id == "created"
    assert sdk_client.pages.created == [
        {
            "parent": {"database_id": "database-1"},
            "properties": {
                "Name": {"title": [{"text": {"content": "Imported Note"}}]},
                "Tags": {"multi_select": [{"name": "Project"}, {"name": "Archive"}]},
            },
        }
    ]


def test_notion_client_can_archive_page() -> None:
    sdk_client = FakeSDKClient()
    notion = NotionClient("notion-key", sdk_client=sdk_client)

    archived = notion.archive_page("page-1")

    assert archived.page_id == "page-1"
    assert archived.title == "Archived"
    assert sdk_client.pages.updated == [{"page_id": "page-1", "archived": True}]


def test_multi_select_properties_discard_blanks_and_preserve_order() -> None:
    assert exception_reason_property(["Empty Title", "No Content", "Empty Title", " "]) == {
        "multi_select": [{"name": "Empty Title"}, {"name": "No Content"}]
    }
    assert import_tags_property(["Project", "Archive"]) == {
        "multi_select": [{"name": "Project"}, {"name": "Archive"}]
    }


def test_unsupported_content_marker_block_uses_error_comment() -> None:
    record = UnsupportedContentRecord(
        note_id="note_000003",
        note_title="Unsupported Note",
        error_comment="Unsupported media payload.",
    )

    assert unsupported_content_marker_block(record) == {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "Unsupported content could not be imported automatically: Unsupported media payload."
                    },
                }
            ],
            "icon": {"type": "emoji", "emoji": "!"},
            "color": "yellow_background",
        },
    }


def test_evernote_embedded_link_marker_block_uses_warning_icon_and_link_text() -> None:
    record = EvernoteEmbeddedLinkRecord(
        note_id="note_000004",
        note_title="Linked Note",
        link_text="Original Evernote Note",
        link_value="evernote:///view/123/s1/guid/guid/",
    )

    assert evernote_embedded_link_marker_block(record) == {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": "Evernote link requires manual resolution: Original Evernote Note"
                    },
                }
            ],
            "icon": {"type": "emoji", "emoji": "⚠️"},
            "color": "yellow_background",
        },
    }


def test_bootstrap_notion_pages_creates_children_under_named_root() -> None:
    root = NotionPageRef(page_id="root", title="Migration Root", url=None, parent_page_id=None)
    client = FakeNotionClient([root])

    result = bootstrap_notion_pages("notion-key", root_title="Migration Root", client=client)

    assert result.root == root
    assert result.converted.title == "Evernote Import"
    assert result.exceptions.title == "Evernote Import Exceptions"
    assert client.created == [("root", "Evernote Import"), ("root", "Evernote Import Exceptions")]


def test_bootstrap_notion_pages_reuses_existing_child_pages() -> None:
    root = NotionPageRef(page_id="root", title="Migration Root", url=None, parent_page_id=None)
    converted = NotionPageRef(page_id="converted", title="Evernote Import", url=None, parent_page_id="root")
    exceptions = NotionPageRef(page_id="exceptions", title="Evernote Import Exceptions", url=None, parent_page_id="root")
    client = FakeNotionClient([root, converted, exceptions])

    result = bootstrap_notion_pages("notion-key", root_title="Migration Root", client=client)

    assert result.converted == converted
    assert result.exceptions == exceptions
    assert client.created == []


def test_bootstrap_notion_pages_uses_workspace_pages_without_root_title() -> None:
    root = NotionPageRef(page_id="root", title="Root", url=None, parent_page_id=None)
    child = NotionPageRef(page_id="child", title="Child", url=None, parent_page_id="root")
    grandchild = NotionPageRef(page_id="grandchild", title="Grandchild", url=None, parent_page_id="child")
    client = FakeNotionClient([root, child, grandchild])

    result = bootstrap_notion_pages("notion-key", client=client)

    assert result.root.title == "Workspace"
    assert result.root.parent_type == "workspace"
    assert client.created == [("workspace", "Evernote Import"), ("workspace", "Evernote Import Exceptions")]


def test_bootstrap_notion_pages_reuses_existing_workspace_pages_without_root_title() -> None:
    converted = NotionPageRef(
        page_id="converted",
        title="Evernote Import",
        url=None,
        parent_page_id=None,
        parent_type="workspace",
    )
    exceptions = NotionPageRef(
        page_id="exceptions",
        title="Evernote Import Exceptions",
        url=None,
        parent_page_id=None,
        parent_type="workspace",
    )
    nested = NotionPageRef(page_id="nested", title="Evernote Import", url=None, parent_page_id="parent")
    client = FakeNotionClient([converted, exceptions, nested])

    result = bootstrap_notion_pages("notion-key", client=client)

    assert result.converted == converted
    assert result.exceptions == exceptions
    assert client.created == []


def test_ensure_import_database_reuses_same_name_under_same_parent() -> None:
    existing = NotionDatabaseRef(
        database_id="existing",
        title="Enduring",
        url=None,
        parent_page_id="converted",
    )
    same_name_elsewhere = NotionDatabaseRef(
        database_id="elsewhere",
        title="Enduring",
        url=None,
        parent_page_id="other",
    )
    client = FakeNotionClient([], databases=[same_name_elsewhere, existing])

    database = ensure_import_database(client, "converted", "Enduring")

    assert database == existing
    assert client.created_databases == []


def test_ensure_import_database_creates_when_same_name_is_only_elsewhere() -> None:
    same_name_elsewhere = NotionDatabaseRef(
        database_id="elsewhere",
        title="Enduring",
        url=None,
        parent_page_id="other",
    )
    client = FakeNotionClient([], databases=[same_name_elsewhere])

    database = ensure_import_database(client, "converted", "Enduring")

    assert database.database_id == "database-created-1"
    assert client.created_databases == [("converted", "Enduring")]


def test_ensure_exception_database_uses_single_import_exceptions_name() -> None:
    client = FakeNotionClient([])

    database = ensure_exception_database(client, "exceptions-page")

    assert database.title == DEFAULT_EXCEPTIONS_DATABASE_TITLE
    assert client.created_databases == [("exceptions-page", "Import-Exceptions")]


def test_notion_bootstrap_cli_reports_pages(monkeypatch, capsys) -> None:
    root = NotionPageRef(page_id="root", title="Root", url=None, parent_page_id=None)
    converted = NotionPageRef(page_id="converted", title="Evernote Import", url=None, parent_page_id="root")
    exceptions = NotionPageRef(page_id="exceptions", title="Evernote Import Exceptions", url=None, parent_page_id="root")

    def fake_bootstrap(notion_key: str, root_title: str | None = None):
        assert notion_key == "notion-key"
        assert root_title == "Root"
        from e2n.notion import NotionBootstrapResult

        return NotionBootstrapResult(root=root, converted=converted, exceptions=exceptions)

    monkeypatch.setattr("e2n.cli.bootstrap_notion_pages", fake_bootstrap)

    exit_code = main(["--notion-bootstrap", "-k", "notion-key", "-n", "Root"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Using Notion root page: Root (root)" in captured.out
    assert "Converted page: Evernote Import (converted)" in captured.out
    assert "Exceptions page: Evernote Import Exceptions (exceptions)" in captured.out


def test_notion_bootstrap_cli_accepts_environment_key(monkeypatch, capsys) -> None:
    root = NotionPageRef(page_id="root", title="Root", url=None, parent_page_id=None)
    converted = NotionPageRef(page_id="converted", title="Evernote Import", url=None, parent_page_id="root")
    exceptions = NotionPageRef(page_id="exceptions", title="Evernote Import Exceptions", url=None, parent_page_id="root")

    def fake_bootstrap(notion_key: str, root_title: str | None = None):
        assert notion_key == "env-key"
        assert root_title == "Root"
        from e2n.notion import NotionBootstrapResult

        return NotionBootstrapResult(root=root, converted=converted, exceptions=exceptions)

    monkeypatch.setenv("NOTION_KEY", "env-key")
    monkeypatch.setattr("e2n.cli.bootstrap_notion_pages", fake_bootstrap)

    exit_code = main(["--notion-bootstrap", "-n", "Root"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Using Notion root page: Root (root)" in captured.out
