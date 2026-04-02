"""Configuration manager — loads, validates, and persists orchestrator config."""

from __future__ import annotations

import copy
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "default_config.yaml"
_USER_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opencode"
_USER_CONFIG_PATH = _USER_CONFIG_DIR / "orchestrator_config.yaml"


@dataclass
class WorkerConfig:
    model: str
    provider: str
    context_window: int
    enabled: bool
    description: str
    temperature: float = 0.7
    tools: list[str] = field(default_factory=list)


@dataclass
class OrchestratorModelConfig:
    model: str
    provider: str
    context_window: int
    endpoint: str


@dataclass
class ResourceConfig:
    max_simultaneous_workers: int
    vram_budget_gb: int
    api_rate_limit_rpm: int
    model_load_timeout_s: int = 120
    worker_generation_timeout_s: int = 300


@dataclass
class ProviderEndpoint:
    endpoint: str
    api_key_env: str | None = None


@dataclass
class FullConfig:
    orchestrator: OrchestratorModelConfig
    workers: dict[str, WorkerConfig]
    resources: ResourceConfig
    providers: dict[str, ProviderEndpoint]


class ConfigManager:
    """Thread-safe singleton config manager with file persistence."""

    _instance: ConfigManager | None = None
    _lock = threading.Lock()
    _config_path_override: str | None = None

    def __new__(cls) -> ConfigManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._config: FullConfig | None = None
        self._raw: dict[str, Any] = {}
        self._load()

    @classmethod
    def set_config_path(cls, path: str) -> None:
        cls._config_path_override = path

    @property
    def config_path(self) -> Path:
        if self._config_path_override:
            return Path(self._config_path_override)
        return _USER_CONFIG_PATH

    # -- Loading ----------------------------------------------------------

    def _load(self) -> None:
        raw = self._read_yaml(_DEFAULT_CONFIG_PATH)
        user_path = self.config_path
        if user_path.exists():
            user_raw = self._read_yaml(user_path)
            raw = self._deep_merge(raw, user_raw)
        self._raw = raw
        self._config = self._parse(raw)

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with open(path) as f:
            return yaml.safe_load(f) or {}

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = copy.deepcopy(base)
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = copy.deepcopy(v)
        return result

    # -- Parsing ----------------------------------------------------------

    def _parse(self, raw: dict[str, Any]) -> FullConfig:
        orch_raw = raw["orchestrator"]
        orchestrator = OrchestratorModelConfig(
            model=orch_raw["model"],
            provider=orch_raw["provider"],
            context_window=orch_raw["context_window"],
            endpoint=orch_raw["endpoint"],
        )

        workers: dict[str, WorkerConfig] = {}
        for role, wraw in raw.get("workers", {}).items():
            workers[role] = WorkerConfig(
                model=wraw["model"],
                provider=wraw["provider"],
                context_window=wraw["context_window"],
                enabled=wraw.get("enabled", True),
                description=wraw.get("description", ""),
                temperature=wraw.get("temperature", 0.7),
                tools=wraw.get("tools", []),
            )

        res_raw = raw.get("resources", {})
        resources = ResourceConfig(
            max_simultaneous_workers=res_raw.get("max_simultaneous_workers", 2),
            vram_budget_gb=res_raw.get("vram_budget_gb", 180),
            api_rate_limit_rpm=res_raw.get("api_rate_limit_rpm", 60),
            model_load_timeout_s=res_raw.get("model_load_timeout_s", 120),
            worker_generation_timeout_s=res_raw.get("worker_generation_timeout_s", 300),
        )

        providers: dict[str, ProviderEndpoint] = {}
        for name, praw in raw.get("providers", {}).items():
            providers[name] = ProviderEndpoint(
                endpoint=praw.get("endpoint", ""),
                api_key_env=praw.get("api_key_env"),
            )

        return FullConfig(
            orchestrator=orchestrator,
            workers=workers,
            resources=resources,
            providers=providers,
        )

    # -- Access -----------------------------------------------------------

    @property
    def cfg(self) -> FullConfig:
        assert self._config is not None
        return self._config

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    def get_worker(self, role: str) -> WorkerConfig | None:
        return self.cfg.workers.get(role)

    def enabled_workers(self) -> dict[str, WorkerConfig]:
        return {r: w for r, w in self.cfg.workers.items() if w.enabled}

    def provider_endpoint(self, provider_name: str) -> ProviderEndpoint | None:
        return self.cfg.providers.get(provider_name)

    # -- Mutation ---------------------------------------------------------

    def update_raw(self, new_raw: dict[str, Any]) -> None:
        """Replace config from raw dict (used by UI), re-parse, and persist."""
        with self._lock:
            self._raw = new_raw
            self._config = self._parse(new_raw)
            self._persist()

    def update_worker(self, role: str, **kwargs: Any) -> None:
        with self._lock:
            if role not in self._raw.get("workers", {}):
                self._raw.setdefault("workers", {})[role] = {}
            for k, v in kwargs.items():
                self._raw["workers"][role][k] = v
            self._config = self._parse(self._raw)
            self._persist()

    def remove_worker(self, role: str) -> None:
        with self._lock:
            self._raw.get("workers", {}).pop(role, None)
            self._config = self._parse(self._raw)
            self._persist()

    def _persist(self) -> None:
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self._raw, f, default_flow_style=False, sort_keys=False)

    # -- Reload -----------------------------------------------------------

    def reload(self) -> None:
        with self._lock:
            self._load()
