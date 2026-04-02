"""Tests for CrewManager integration layer."""

import tempfile

import yaml

from goose_orchestrator.config_manager import ConfigManager
from goose_orchestrator.crew_manager import _build_llm_string, StepResult


def _reset(path: str):
    ConfigManager._instance = None
    ConfigManager._config_path_override = path


def _make_config() -> str:
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
        yaml.dump({}, f)
        return f.name


def test_build_llm_string_ollama():
    path = _make_config()
    _reset(path)
    cfg = ConfigManager()
    result = _build_llm_string("ollama", "qwen3:14b", cfg)
    assert result == "ollama/qwen3:14b"


def test_build_llm_string_anthropic():
    path = _make_config()
    _reset(path)
    cfg = ConfigManager()
    result = _build_llm_string("anthropic", "claude-sonnet-4-6", cfg)
    assert result == "anthropic/claude-sonnet-4-6"


def test_build_llm_string_openai():
    path = _make_config()
    _reset(path)
    cfg = ConfigManager()
    result = _build_llm_string("openai", "gpt-4o", cfg)
    assert result == "gpt-4o"


def test_step_result_dataclass():
    r = StepResult(
        step_id=1, role="code_gen", model="test:7b",
        text="hello", input_tokens=10, output_tokens=20,
        elapsed_s=1.5, success=True,
    )
    assert r.success
    assert r.error is None


def test_step_result_failure():
    r = StepResult(
        step_id=2, role="deep_research", model="test:32b",
        text="", input_tokens=0, output_tokens=0,
        elapsed_s=5.0, success=False, error="Connection refused",
    )
    assert not r.success
    assert "Connection" in r.error
