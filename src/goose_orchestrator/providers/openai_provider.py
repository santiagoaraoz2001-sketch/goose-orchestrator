"""OpenAI-compatible provider (works with OpenAI, vLLM, LM Studio, etc.)."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial

import requests

from goose_orchestrator.providers.base import BaseProvider, GenerateRequest, GenerateResponse

log = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Stateless API provider — no local VRAM cost."""

    @property
    def is_local(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "")
        h: dict[str, str] = {"Content-Type": "application/json"}
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    async def _post(self, path: str, json: dict, timeout: int = 300) -> dict:
        loop = asyncio.get_event_loop()

        def _do() -> requests.Response:
            return requests.post(
                f"{self.endpoint}{path}",
                json=json,
                headers=self._headers(),
                timeout=timeout,
            )

        resp = await loop.run_in_executor(None, _do)
        resp.raise_for_status()
        return resp.json()

    # -- Model lifecycle (no-ops for API) ---------------------------------

    async def is_model_loaded(self, model: str) -> bool:
        return True  # API models are always "loaded"

    async def load_model(self, model: str) -> None:
        pass

    async def unload_model(self, model: str) -> None:
        pass

    async def list_models(self) -> list[str]:
        try:
            loop = asyncio.get_event_loop()

            def _do() -> requests.Response:
                return requests.get(
                    f"{self.endpoint}/models",
                    headers=self._headers(),
                    timeout=30,
                )

            resp = await loop.run_in_executor(None, _do)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return []

    # -- Generation -------------------------------------------------------

    async def generate(self, req: GenerateRequest) -> GenerateResponse:
        messages: list[dict] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        payload: dict = {
            "model": req.model,
            "messages": messages,
            "max_tokens": req.max_tokens,
            "temperature": req.temperature,
            "stream": False,
        }
        if req.stop:
            payload["stop"] = req.stop
        if req.json_mode:
            payload["response_format"] = {"type": "json_object"}

        data = await self._post("/chat/completions", payload)

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return GenerateResponse(
            text=choice["message"]["content"],
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=data.get("model", req.model),
            finish_reason=choice.get("finish_reason", ""),
        )
