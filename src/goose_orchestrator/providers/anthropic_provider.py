"""Anthropic provider for Claude models."""

from __future__ import annotations

import asyncio
import logging
import os
from functools import partial

import requests

from goose_orchestrator.providers.base import BaseProvider, GenerateRequest, GenerateResponse

log = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """Stateless API provider for Anthropic's Claude family."""

    @property
    def is_local(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        return {
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }

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
        return True

    async def load_model(self, model: str) -> None:
        pass

    async def unload_model(self, model: str) -> None:
        pass

    async def list_models(self) -> list[str]:
        return [
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        ]

    # -- Generation -------------------------------------------------------

    async def generate(self, req: GenerateRequest) -> GenerateResponse:
        payload: dict = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": [{"role": "user", "content": req.prompt}],
        }
        if req.system:
            payload["system"] = req.system
        if req.temperature is not None:
            payload["temperature"] = req.temperature

        data = await self._post("/v1/messages", payload)

        text_parts = [
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        usage = data.get("usage", {})

        return GenerateResponse(
            text="".join(text_parts),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            model=data.get("model", req.model),
            finish_reason=data.get("stop_reason", ""),
        )
