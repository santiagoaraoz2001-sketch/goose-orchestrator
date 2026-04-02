"""Tests for ModelPool VRAM tracking and LRU eviction logic."""

import asyncio
import tempfile
from unittest.mock import AsyncMock, patch

import yaml

from opencode_orchestrator.config_manager import ConfigManager
from opencode_orchestrator.model_pool import ModelPool


def _reset_singletons(config_path: str):
    ConfigManager._instance = None
    ConfigManager._config_path_override = config_path
    from opencode_orchestrator.orchestrator import Orchestrator
    Orchestrator._instance = None


def _make_config(overrides: dict | None = None) -> str:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(overrides or {}, f)
        return f.name


def test_pool_initial_state():
    path = _make_config()
    _reset_singletons(path)

    pool = ModelPool()
    assert pool.used_vram == 0
    assert pool.available_vram == 180  # default budget


def test_pool_status_format():
    path = _make_config()
    _reset_singletons(path)

    pool = ModelPool()
    s = pool.status()
    assert "vram_budget_gb" in s
    assert "loaded_models" in s
    assert isinstance(s["loaded_models"], list)


def test_pool_vram_accounting():
    """Test that VRAM tracking correctly sums loaded models."""
    path = _make_config()
    _reset_singletons(path)

    pool = ModelPool()

    # Simulate loaded models by directly manipulating internal state
    from opencode_orchestrator.model_pool import LoadedModel
    from opencode_orchestrator.providers.ollama_provider import OllamaProvider
    import time

    mock_provider = OllamaProvider(endpoint="http://localhost:11434")

    pool._loaded["model_a"] = LoadedModel(
        model="model_a", provider_name="ollama", provider=mock_provider,
        vram_gb=20.0, last_used=time.monotonic(), is_orchestrator=True,
    )
    pool._loaded["model_b"] = LoadedModel(
        model="model_b", provider_name="ollama", provider=mock_provider,
        vram_gb=10.0, last_used=time.monotonic(),
    )

    assert pool.used_vram == 30.0
    assert pool.available_vram == 150.0


def test_lru_victim_skips_orchestrator():
    """LRU eviction should never evict the orchestrator model."""
    path = _make_config()
    _reset_singletons(path)

    pool = ModelPool()

    from opencode_orchestrator.model_pool import LoadedModel
    from opencode_orchestrator.providers.ollama_provider import OllamaProvider
    import time

    mock_provider = OllamaProvider(endpoint="http://localhost:11434")

    # Orchestrator loaded first (oldest)
    pool._loaded["orch"] = LoadedModel(
        model="orch", provider_name="ollama", provider=mock_provider,
        vram_gb=10.0, last_used=time.monotonic() - 100, is_orchestrator=True,
    )
    # Worker loaded second
    pool._loaded["worker"] = LoadedModel(
        model="worker", provider_name="ollama", provider=mock_provider,
        vram_gb=20.0, last_used=time.monotonic() - 50,
    )

    victim = pool._find_lru_victim(exclude_orchestrator=True)
    assert victim == "worker"  # Should pick worker, not orchestrator
