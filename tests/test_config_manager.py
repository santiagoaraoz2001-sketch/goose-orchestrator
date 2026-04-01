"""Tests for ConfigManager."""

import tempfile
from pathlib import Path

import yaml

from goose_orchestrator.config_manager import ConfigManager


def _fresh_manager(config_path: str) -> ConfigManager:
    """Create a fresh ConfigManager pointing at a temp config file."""
    # Reset singleton
    ConfigManager._instance = None
    ConfigManager._config_path_override = config_path
    return ConfigManager()


def test_loads_default_config():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"")  # empty user config → pure defaults
        path = f.name

    mgr = _fresh_manager(path)
    cfg = mgr.cfg

    assert cfg.orchestrator.model == "qwen3:14b"
    assert cfg.orchestrator.provider == "ollama"
    assert "deep_research" in cfg.workers
    assert "code_gen" in cfg.workers
    assert cfg.resources.max_simultaneous_workers == 2


def test_user_config_overrides_defaults():
    override = {
        "orchestrator": {"model": "custom:7b"},
        "resources": {"max_simultaneous_workers": 4},
    }
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump(override, f)
        path = f.name

    mgr = _fresh_manager(path)

    assert mgr.cfg.orchestrator.model == "custom:7b"
    # non-overridden fields should retain defaults
    assert mgr.cfg.orchestrator.provider == "ollama"
    assert mgr.cfg.resources.max_simultaneous_workers == 4


def test_update_worker():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"")
        path = f.name

    mgr = _fresh_manager(path)
    mgr.update_worker("code_gen", model="deepseek-coder:33b", temperature=0.2)

    assert mgr.cfg.workers["code_gen"].model == "deepseek-coder:33b"
    assert mgr.cfg.workers["code_gen"].temperature == 0.2

    # Verify persistence
    with open(path) as f:
        raw = yaml.safe_load(f)
    assert raw["workers"]["code_gen"]["model"] == "deepseek-coder:33b"


def test_add_and_remove_worker():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"")
        path = f.name

    mgr = _fresh_manager(path)

    # Add new role
    mgr.update_worker("data_analysis", model="qwen3:14b", provider="ollama",
                       context_window=16384, temperature=0.5, enabled=True,
                       description="Data analysis and visualization")

    assert "data_analysis" in mgr.cfg.workers
    assert mgr.cfg.workers["data_analysis"].model == "qwen3:14b"

    # Remove it
    mgr.remove_worker("data_analysis")
    assert "data_analysis" not in mgr.cfg.workers


def test_enabled_workers_filter():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"")
        path = f.name

    mgr = _fresh_manager(path)
    mgr.update_worker("creative", enabled=False)

    enabled = mgr.enabled_workers()
    assert "creative" not in enabled
    assert "code_gen" in enabled


def test_temperature_per_worker():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
        f.write(b"")
        path = f.name

    mgr = _fresh_manager(path)

    # Check default temperatures from config
    assert mgr.cfg.workers["math_reasoning"].temperature == 0.1
    assert mgr.cfg.workers["creative"].temperature == 0.9
    assert mgr.cfg.workers["code_gen"].temperature == 0.3
