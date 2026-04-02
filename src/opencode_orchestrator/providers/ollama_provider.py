"""Ollama provider — local model management with explicit VRAM control."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import requests

from opencode_orchestrator.providers.base import BaseProvider, GenerateRequest, GenerateResponse

log = logging.getLogger(__name__)

# Rough parameter-count → VRAM mapping (in GB, Q4 quantisation assumed).
_SIZE_HINTS: dict[str, float] = {
    "1b": 1.0, "3b": 2.5, "7b": 5.0, "8b": 5.5,
    "13b": 9.0, "14b": 10.0, "32b": 20.0, "34b": 22.0,
    "70b": 42.0, "72b": 44.0, "110b": 65.0,
}


def _estimate_vram(model_name: str) -> float:
    """Best-effort VRAM estimate from the model tag."""
    lower = model_name.lower()
    for tag, gb in sorted(_SIZE_HINTS.items(), key=lambda x: -x[1]):
        if tag in lower:
            return gb
    return 8.0  # conservative default


class OllamaProvider(BaseProvider):
    """Manages local Ollama models with keep_alive-based VRAM control."""

    @property
    def is_local(self) -> bool:
        return True

    def _sync_post(self, path: str, json: dict, timeout: int = 120) -> requests.Response:
        return requests.post(f"{self.endpoint}{path}", json=json, timeout=timeout)

    def _sync_get(self, path: str, timeout: int = 30) -> requests.Response:
        return requests.get(f"{self.endpoint}{path}", timeout=timeout)

    async def _post(self, path: str, json: dict, timeout: int = 120) -> dict:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, partial(self._sync_post, path, json, timeout))
        resp.raise_for_status()
        return resp.json()

    async def _get(self, path: str) -> dict:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, partial(self._sync_get, path))
        resp.raise_for_status()
        return resp.json()

    # -- Model lifecycle --------------------------------------------------

    async def is_model_loaded(self, model: str) -> bool:
        try:
            data = await self._get("/api/ps")
            running = data.get("models", [])
            return any(m.get("name", "").startswith(model) for m in running)
        except Exception:
            return False

    async def load_model(self, model: str) -> None:
        """Load model into VRAM by sending an empty generate with keep_alive=-1."""
        log.info("Loading model %s into VRAM", model)
        await self._post(
            "/api/generate",
            {"model": model, "prompt": "", "keep_alive": -1},
            timeout=300,
        )
        log.info("Model %s loaded", model)

    async def unload_model(self, model: str) -> None:
        """Evict model from VRAM by setting keep_alive=0."""
        log.info("Unloading model %s from VRAM", model)
        try:
            await self._post(
                "/api/generate",
                {"model": model, "prompt": "", "keep_alive": 0},
                timeout=30,
            )
        except Exception as e:
            log.warning("Failed to unload %s: %s", model, e)

    async def list_models(self) -> list[str]:
        data = await self._get("/api/tags")
        return [m["name"] for m in data.get("models", [])]

    async def model_vram_gb(self, model: str) -> float:
        return _estimate_vram(model)

    # -- Generation -------------------------------------------------------

    async def _get_model_max_ctx(self, model: str) -> int:
        """Query the model's declared max context length from Ollama metadata."""
        try:
            data = await self._post("/api/show", {"name": model}, timeout=10)
            model_info = data.get("model_info", {})
            for k, v in model_info.items():
                if "context" in k.lower() and "length" in k.lower():
                    return int(v)
        except Exception:
            pass
        return 4096  # fallback

    async def generate(self, req: GenerateRequest) -> GenerateResponse:
        # Set num_ctx to the model's true max so Ollama doesn't truncate at 4096
        max_ctx = await self._get_model_max_ctx(req.model)

        payload: dict = {
            "model": req.model,
            "prompt": req.prompt,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "temperature": req.temperature,
                "num_predict": req.max_tokens,
                "num_ctx": max_ctx,
            },
        }
        if req.system:
            payload["system"] = req.system
        if req.stop:
            payload["options"]["stop"] = req.stop
        if req.json_mode:
            payload["format"] = "json"

        data = await self._post("/api/generate", payload, timeout=600)

        return GenerateResponse(
            text=data.get("response", ""),
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            model=req.model,
            finish_reason="stop",
        )
