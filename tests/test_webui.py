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
