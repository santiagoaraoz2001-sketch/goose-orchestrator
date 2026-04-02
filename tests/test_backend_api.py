"""Tests for the FastAPI backend endpoints."""

import tempfile
from unittest.mock import patch, AsyncMock

import pytest
import yaml
from fastapi.testclient import TestClient

from goose_orchestrator.config_manager import ConfigManager


def _reset_singletons(config_path: str):
    ConfigManager._instance = None
    ConfigManager._config_path_override = config_path
    from goose_orchestrator.orchestrator import Orchestrator
    Orchestrator._instance = None


def _make_config() -> str:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({}, f)
        return f.name


@pytest.fixture(autouse=True)
def fresh_config():
    path = _make_config()
    _reset_singletons(path)
    yield path


@pytest.fixture
def client():
    from goose_orchestrator.backend.app import app
    return TestClient(app)


# ── Config endpoints ─────────────────────────────────────────────────────────

def test_get_config(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "orchestrator" in data
    assert "workers" in data


def test_get_workers(client):
    resp = client.get("/api/config/workers")
    assert resp.status_code == 200
    data = resp.json()
    assert "code_gen" in data
    assert "deep_research" in data


def test_patch_worker(client):
    resp = client.patch("/api/config/workers/code_gen", json={"temperature": 0.1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["temperature"] == 0.1


def test_patch_worker_empty_body(client):
    resp = client.patch("/api/config/workers/code_gen", json={})
    assert resp.status_code == 400


def test_create_worker(client):
    resp = client.post("/api/config/workers/custom_role", json={
        "model": "test:7b", "provider": "ollama",
        "context_window": 8192, "temperature": 0.5,
        "enabled": True, "description": "Test role",
    })
    assert resp.status_code == 201


def test_create_duplicate_worker(client):
    resp = client.post("/api/config/workers/code_gen", json={
        "model": "test:7b", "provider": "ollama",
        "context_window": 8192, "temperature": 0.5,
        "enabled": True, "description": "Duplicate",
    })
    assert resp.status_code == 409


def test_delete_worker(client):
    resp = client.delete("/api/config/workers/creative")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == "creative"

    resp2 = client.delete("/api/config/workers/creative")
    assert resp2.status_code == 404


def test_patch_orchestrator(client):
    resp = client.patch("/api/config/orchestrator", json={"model": "new-model:14b"})
    assert resp.status_code == 200
    assert resp.json()["model"] == "new-model:14b"


def test_patch_resources(client):
    resp = client.patch("/api/config/resources", json={"max_simultaneous_workers": 4})
    assert resp.status_code == 200
    assert resp.json()["max_simultaneous_workers"] == 4


def test_patch_provider(client):
    resp = client.patch("/api/config/providers/ollama", json={"endpoint": "http://custom:11434"})
    assert resp.status_code == 200
    assert resp.json()["endpoint"] == "http://custom:11434"


# ── Status endpoint ──────────────────────────────────────────────────────────

def test_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "vram_budget_gb" in data
    assert "loaded_models" in data


# ── Orchestrate REST endpoint ────────────────────────────────────────────────

def test_orchestrate_no_ollama(client):
    """Orchestrate will fail gracefully if Ollama isn't running."""
    resp = client.post("/api/orchestrate", json={"prompt": "test"})
    # Should return 500 with error message (Ollama not running)
    assert resp.status_code == 500
    assert "error" in resp.json()


# ── Model listing ────────────────────────────────────────────────────────────

def test_list_models_invalid_provider(client):
    resp = client.get("/api/models/nonexistent")
    assert resp.status_code == 200
    data = resp.json()
    assert "error" in data or data["models"] == []
