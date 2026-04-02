"""VRAM-aware model pool with LRU eviction and speculative preloading."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass

from opencode_orchestrator.config_manager import ConfigManager
from opencode_orchestrator.providers import create_provider
from opencode_orchestrator.providers.base import BaseProvider

log = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    """Tracks a model currently occupying VRAM."""
    model: str
    provider_name: str
    provider: BaseProvider
    vram_gb: float
    last_used: float  # monotonic timestamp
    is_orchestrator: bool = False


class ModelPool:
    """Manages model lifecycle with a strict VRAM budget.

    Invariants:
    - Total VRAM of loaded local models never exceeds `vram_budget_gb`
    - The orchestrator model is pinned and never evicted
    - Worker models are evicted LRU-first when space is needed
    - API-backed models (OpenAI, Anthropic) bypass the pool entirely
    """

    def __init__(self) -> None:
        cfg = ConfigManager()
        self._vram_budget = cfg.cfg.resources.vram_budget_gb
        # OrderedDict preserves insertion order; we move-to-end on access for LRU
        self._loaded: OrderedDict[str, LoadedModel] = OrderedDict()
        self._lock = asyncio.Lock()
        self._providers: dict[str, BaseProvider] = {}

    def _get_provider(self, provider_name: str, model: str) -> BaseProvider:
        """Get or create a provider instance."""
        cfg = ConfigManager()
        ep = cfg.provider_endpoint(provider_name)
        endpoint = ep.endpoint if ep else ""
        api_key = None
        if ep and ep.api_key_env:
            api_key = os.environ.get(ep.api_key_env)

        key = f"{provider_name}:{endpoint}"
        if key not in self._providers:
            self._providers[key] = create_provider(provider_name, endpoint, api_key)
        return self._providers[key]

    @property
    def used_vram(self) -> float:
        return sum(m.vram_gb for m in self._loaded.values() if m.provider.is_local)

    @property
    def available_vram(self) -> float:
        return self._vram_budget - self.used_vram

    # -- Public API -------------------------------------------------------

    async def ensure_orchestrator_loaded(self) -> BaseProvider:
        """Load the orchestrator model and pin it (never evicted)."""
        cfg = ConfigManager()
        orch = cfg.cfg.orchestrator
        provider = self._get_provider(orch.provider, orch.model)

        async with self._lock:
            if orch.model in self._loaded:
                self._loaded.move_to_end(orch.model)
                return provider

            if provider.is_local:
                vram = await provider.model_vram_gb(orch.model)
                await self._make_room(vram, exclude_orchestrator=False)
                await provider.load_model(orch.model)
                self._loaded[orch.model] = LoadedModel(
                    model=orch.model,
                    provider_name=orch.provider,
                    provider=provider,
                    vram_gb=vram,
                    last_used=time.monotonic(),
                    is_orchestrator=True,
                )
            return provider

    async def acquire_worker(self, role: str) -> tuple[BaseProvider, str]:
        """Load a worker model for the given role, evicting others if needed.

        Returns (provider, model_name).
        """
        cfg = ConfigManager()
        worker_cfg = cfg.get_worker(role)
        if worker_cfg is None:
            raise ValueError(f"Unknown worker role: {role!r}")

        provider = self._get_provider(worker_cfg.provider, worker_cfg.model)
        model = worker_cfg.model

        async with self._lock:
            if model in self._loaded:
                entry = self._loaded[model]
                entry.last_used = time.monotonic()
                self._loaded.move_to_end(model)
                return provider, model

            if provider.is_local:
                vram = await provider.model_vram_gb(model)
                await self._make_room(vram, exclude_orchestrator=True)
                await provider.load_model(model)
                self._loaded[model] = LoadedModel(
                    model=model,
                    provider_name=worker_cfg.provider,
                    provider=provider,
                    vram_gb=vram,
                    last_used=time.monotonic(),
                )
            return provider, model

    async def release_worker(self, model: str) -> None:
        """Mark a worker as no longer actively generating (but keep warm)."""
        async with self._lock:
            if model in self._loaded:
                self._loaded[model].last_used = time.monotonic()

    async def preload_hint(self, role: str) -> None:
        """Speculatively start loading a model in the background.

        Called by the orchestrator when it predicts the next worker needed.
        Non-blocking — fires and forgets.
        """
        try:
            await self.acquire_worker(role)
        except Exception as e:
            log.debug("Preload hint for %s failed (non-critical): %s", role, e)

    async def unload_all_workers(self) -> None:
        """Evict all non-orchestrator models."""
        async with self._lock:
            to_remove = [k for k, v in self._loaded.items() if not v.is_orchestrator]
            for key in to_remove:
                await self._evict(key)

    def status(self) -> dict:
        """Return current pool state for the status tool."""
        return {
            "vram_budget_gb": self._vram_budget,
            "used_vram_gb": round(self.used_vram, 1),
            "available_vram_gb": round(self.available_vram, 1),
            "loaded_models": [
                {
                    "model": m.model,
                    "provider": m.provider_name,
                    "vram_gb": round(m.vram_gb, 1),
                    "is_orchestrator": m.is_orchestrator,
                    "idle_seconds": round(time.monotonic() - m.last_used, 1),
                }
                for m in self._loaded.values()
            ],
        }

    # -- Internal ---------------------------------------------------------

    async def _make_room(self, needed_gb: float, exclude_orchestrator: bool) -> None:
        """Evict LRU models until `needed_gb` is available."""
        while self.available_vram < needed_gb:
            victim = self._find_lru_victim(exclude_orchestrator)
            if victim is None:
                log.warning(
                    "Cannot free %.1f GB — only %.1f GB available after evicting all eligible models",
                    needed_gb, self.available_vram,
                )
                break
            await self._evict(victim)

    def _find_lru_victim(self, exclude_orchestrator: bool) -> str | None:
        """Find the least-recently-used local model eligible for eviction."""
        for key, entry in self._loaded.items():
            if exclude_orchestrator and entry.is_orchestrator:
                continue
            if not entry.provider.is_local:
                continue
            return key  # OrderedDict: first item is oldest
        return None

    async def _evict(self, key: str) -> None:
        entry = self._loaded.pop(key, None)
        if entry is None:
            return
        log.info("Evicting model %s (%.1f GB)", entry.model, entry.vram_gb)
        try:
            await entry.provider.unload_model(entry.model)
        except Exception as e:
            log.warning("Failed to unload %s: %s", entry.model, e)
