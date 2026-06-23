"""Tests for WebUI wizard workflow."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from e2n.webui.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


# --- Step navigation and gating ---


def test_wizard_root_shows_step_1(client) -> None:
    """GET /wizard/ should display the first step (source configuration)."""
    response = client.get("/wizard/")
    assert response.status_code == 200
    assert "Configure Source" in response.text


def test_wizard_step_2_blocked_without_step_1(client) -> None:
    """GET /wizard/step/2 before step 1 complete should redirect to step 1."""
    response = client.get("/wizard/step/2", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert "/wizard/" in response.headers.get("location", "")


def test_wizard_step_1_post_valid_source(client, tmp_path) -> None:
    """POST /wizard/step/1 with valid enex path should advance wizard state."""
    source = tmp_path / "Test.enex"
    source.write_text("<en-export></en-export>", encoding="utf-8")

    response = client.post(
        "/wizard/step/1",
        data={"enex_source": str(source), "processing_directory": str(tmp_path / "proc")},
        follow_redirects=False,
    )
    # Should redirect to step 2 on success
    assert response.status_code in (302, 303)
    assert "step/2" in response.headers.get("location", "")


def test_wizard_step_1_post_invalid_source(client, tmp_path) -> None:
    """POST /wizard/step/1 with non-existent path should show error."""
    response = client.post(
        "/wizard/step/1",
        data={"enex_source": "/nonexistent/path.enex", "processing_directory": str(tmp_path)},
    )
    assert response.status_code == 200
    assert "error" in response.text.lower() or "not found" in response.text.lower() or "does not exist" in response.text.lower()


# --- Notion connection step ---


def test_wizard_step_2_shows_notion_config(client, tmp_path) -> None:
    """GET /wizard/step/2 (when step 1 is done) should show Notion key input."""
    # First complete step 1
    source = tmp_path / "Test.enex"
    source.write_text("<en-export></en-export>", encoding="utf-8")
    client.post(
        "/wizard/step/1",
        data={"enex_source": str(source), "processing_directory": str(tmp_path / "proc")},
    )

    response = client.get("/wizard/step/2")
    assert response.status_code == 200
    assert "notion" in response.text.lower()



# --- Notion connection test ---


def test_wizard_step_2_post_test_connection_success(client, tmp_path, monkeypatch) -> None:
    """POST /wizard/step/2 with valid key should report connection success."""
    # Complete step 1 first
    source = tmp_path / "Test.enex"
    source.write_text("<en-export></en-export>", encoding="utf-8")
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(tmp_path / "proc")})

    # Mock the Notion API connection test
    from unittest.mock import MagicMock, patch
    mock_client = MagicMock()
    mock_client.search_pages.return_value = []

    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        response = client.post(
            "/wizard/step/2",
            data={"notion_key": "ntn_test_key_123", "notion_root": ""},
            follow_redirects=False,
        )

    assert response.status_code in (200, 302, 303)
    # If 200, should show success; if redirect, step 2 is complete
    if response.status_code == 200:
        assert "success" in response.text.lower() or "connected" in response.text.lower()


def test_wizard_step_2_post_test_connection_failure(client, tmp_path, monkeypatch) -> None:
    """POST /wizard/step/2 with bad key should show connection error."""
    source = tmp_path / "Test.enex"
    source.write_text("<en-export></en-export>", encoding="utf-8")
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(tmp_path / "proc")})

    from unittest.mock import patch
    with patch("e2n.webui.app.NotionClient", side_effect=Exception("Invalid token")):
        response = client.post(
            "/wizard/step/2",
            data={"notion_key": "bad_key", "notion_root": ""},
        )

    assert response.status_code == 200
    assert "error" in response.text.lower() or "failed" in response.text.lower() or "invalid" in response.text.lower()


# --- Progress endpoint ---


def test_wizard_progress_endpoint_returns_json(client, tmp_path) -> None:
    """GET /wizard/progress should return JSON with progress data."""
    source = tmp_path / "Test.enex"
    source.write_text(
        '<?xml version="1.0"?><en-export><note><title>N1</title>'
        '<content><![CDATA[<?xml version="1.0"?><en-note>x</en-note>]]></content></note></en-export>',
        encoding="utf-8",
    )
    proc_dir = tmp_path / "proc"

    # Complete step 1 to set processing dir
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(proc_dir)})

    response = client.get("/wizard/progress")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "total_notes" in data



# --- Step 3: Extract trigger ---


def test_wizard_step_3_triggers_extraction(client, tmp_path) -> None:
    """POST /wizard/step/3 should run extraction and redirect to step 4."""
    source = tmp_path / "Extract.enex"
    source.write_text(
        '<?xml version="1.0"?><en-export><note><title>Note1</title>'
        '<content><![CDATA[<?xml version="1.0"?><en-note>hello</en-note>]]></content></note></en-export>',
        encoding="utf-8",
    )
    proc_dir = tmp_path / "proc"

    # Complete steps 1 and 2
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(proc_dir)})
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.search_pages.return_value = []
    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        client.post("/wizard/step/2", data={"notion_key": "ntn_test", "notion_root": ""})

    # Trigger extraction
    response = client.post("/wizard/step/3", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "step/4" in response.headers.get("location", "") or "step/3" in response.headers.get("location", "")

    # Extraction should have created processing output
    assert (proc_dir / "Extract" / "state.db").exists()
    assert (proc_dir / "Extract" / "master.txt").exists()


def test_wizard_step_3_blocked_without_step_2(client, tmp_path) -> None:
    """GET /wizard/step/3 before step 2 complete should redirect."""
    source = tmp_path / "T.enex"
    source.write_text("<en-export></en-export>", encoding="utf-8")
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(tmp_path / "p")})

    response = client.get("/wizard/step/3", follow_redirects=False)
    assert response.status_code in (302, 303)


# --- Step 4: Import trigger ---


def test_wizard_step_4_shows_import_page(client, tmp_path) -> None:
    """GET /wizard/step/4 (after extraction) should show import controls."""
    source = tmp_path / "Imp.enex"
    source.write_text(
        '<?xml version="1.0"?><en-export><note><title>N</title>'
        '<content><![CDATA[<?xml version="1.0"?><en-note>x</en-note>]]></content></note></en-export>',
        encoding="utf-8",
    )
    proc_dir = tmp_path / "proc"

    # Complete steps 1, 2, 3
    client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(proc_dir)})
    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.search_pages.return_value = []
    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        client.post("/wizard/step/2", data={"notion_key": "ntn_test", "notion_root": ""})
    client.post("/wizard/step/3")

    response = client.get("/wizard/step/4")
    assert response.status_code == 200
    assert "import" in response.text.lower()



# --- Step 4: Import trigger ---


def test_wizard_step_4_post_triggers_import(client, tmp_path) -> None:
    """POST /wizard/step/4 should run import (mocked Notion) and redirect to step 5."""
    source = tmp_path / "Imp.enex"
    source.write_text(
        '<?xml version="1.0"?><en-export><note><title>N</title>'
        '<content><![CDATA[<?xml version="1.0"?><en-note>text</en-note>]]></content></note></en-export>',
        encoding="utf-8",
    )
    proc_dir = tmp_path / "proc"

    from unittest.mock import patch, MagicMock
    from e2n.notion import NotionPageRef, NotionDatabaseRef, NotionBootstrapResult

    mock_client = MagicMock()
    mock_client.search_pages.return_value = []
    mock_client.search_databases.return_value = []
    mock_client.import_note_blocks.return_value = "page-id-1"
    mock_client.list_block_children.return_value = []

    mock_bootstrap = NotionBootstrapResult(
        root=NotionPageRef(page_id="root-1", title="Root", url=None, parent_page_id=None),
        converted=NotionPageRef(page_id="conv-1", title="Evernote Import", url=None, parent_page_id="root-1"),
        exceptions=NotionPageRef(page_id="exc-1", title="Evernote Import Exceptions", url=None, parent_page_id="root-1"),
    )
    mock_import_db = NotionDatabaseRef(database_id="db-1", title="Imp", url=None, parent_page_id="conv-1")
    mock_exc_db = NotionDatabaseRef(database_id="exc-db-1", title="Import-Exceptions", url=None, parent_page_id="exc-1")

    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(proc_dir)})
        client.post("/wizard/step/2", data={"notion_key": "ntn_k", "notion_root": ""})

    client.post("/wizard/step/3")  # extract

    with patch("e2n.webui.app.NotionClient", return_value=mock_client), \
         patch("e2n.webui.app.bootstrap_notion_pages", return_value=mock_bootstrap), \
         patch("e2n.webui.app.ensure_import_database", return_value=mock_import_db), \
         patch("e2n.webui.app.ensure_exception_database", return_value=mock_exc_db):
        response = client.post("/wizard/step/4", follow_redirects=False)

    assert response.status_code in (302, 303)
    assert "step/5" in response.headers.get("location", "")


# --- Step 5: Review ---


def test_wizard_step_5_shows_exception_summary(client, tmp_path) -> None:
    """GET /wizard/step/5 should display exception summary."""
    source = tmp_path / "Rev.enex"
    source.write_text(
        '<?xml version="1.0"?><en-export><note><title>  </title>'
        '<content><![CDATA[<?xml version="1.0"?><en-note></en-note>]]></content></note></en-export>',
        encoding="utf-8",
    )
    proc_dir = tmp_path / "proc"

    from unittest.mock import patch, MagicMock
    mock_client = MagicMock()
    mock_client.search_pages.return_value = []
    mock_client.search_databases.return_value = []
    mock_client._sdk_client = MagicMock()
    mock_client._sdk_client.pages.create.return_value = {"id": "p1", "url": "https://notion.so/p"}
    mock_client._sdk_client.databases.create.return_value = {
        "id": "db1", "url": "https://notion.so/db", "title": [{"text": {"content": "Rev"}}],
        "parent": {"page_id": "par1"},
    }
    mock_client._sdk_client.blocks.children.list.return_value = {"results": [], "has_more": False}

    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        client.post("/wizard/step/1", data={"enex_source": str(source), "processing_directory": str(proc_dir)})
        client.post("/wizard/step/2", data={"notion_key": "ntn_k", "notion_root": ""})

    client.post("/wizard/step/3")

    with patch("e2n.webui.app.NotionClient", return_value=mock_client):
        client.post("/wizard/step/4")

    response = client.get("/wizard/step/5")
    assert response.status_code == 200
    assert "review" in response.text.lower() or "exception" in response.text.lower() or "complete" in response.text.lower()
