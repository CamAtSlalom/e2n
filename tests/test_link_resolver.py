from pathlib import Path

from e2n.link_resolver import block_id_from_url, read_evernote_link_exceptions, resolve_evernote_links
from e2n.notion import NotionPageRef


class FakeResolverClient:
    def __init__(self) -> None:
        self.updated: list[tuple[str, str, str]] = []

    def search_pages(self, query: str | None = None):
        if query == "Target Note":
            return [NotionPageRef(page_id="page-1", title="Target Note", url="https://notion.so/page-1", parent_page_id=None)]
        return []

    def update_block_with_page_link(self, block_id: str, link_text: str, page_url: str):
        self.updated.append((block_id, link_text, page_url))
        return {}


def test_read_evernote_link_exceptions_filters_link_rows(tmp_path: Path) -> None:
    exceptions_file = tmp_path / "exceptions.txt"
    exceptions_file.write_text(
        "\n".join(
            [
                "note_1\tNote\tNo Content\t/source.enex\t\t\t",
                "note_2\tNote\tEvernote Link\t/source.enex\thttps://notion.so/p#abc123\tTarget Note\tevernote:/view/x",
            ]
        ),
        encoding="utf-8",
    )

    records = read_evernote_link_exceptions(exceptions_file)

    assert len(records) == 1
    assert records[0].link_text == "Target Note"
    assert records[0].link_value == "evernote:/view/x"


def test_resolve_evernote_links_updates_placeholder_when_match_and_block_url_exist(tmp_path: Path) -> None:
    exceptions_file = tmp_path / "exceptions.txt"
    exceptions_file.write_text(
        "note_2\tNote\tEvernote Link\t/source.enex\thttps://notion.so/p#abc-123\tTarget Note\tevernote:/view/x\n",
        encoding="utf-8",
    )
    client = FakeResolverClient()

    results = resolve_evernote_links(exceptions_file, "notion-key", client=client)

    assert results[0].updated is True
    assert client.updated == [("abc123", "Target Note", "https://notion.so/page-1")]


def test_block_id_from_url_returns_empty_without_fragment() -> None:
    assert block_id_from_url("https://notion.so/page") == ""
