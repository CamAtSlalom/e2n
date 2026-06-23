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
