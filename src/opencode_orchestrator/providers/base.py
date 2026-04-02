"""Abstract provider interface for LLM backends."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class GenerateRequest:
    model: str
    prompt: str
    system: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    stop: list[str] = field(default_factory=list)
    json_mode: bool = False


@dataclass
class GenerateResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    finish_reason: str = ""


class BaseProvider(abc.ABC):
    """Common interface every provider must implement."""

    def __init__(self, endpoint: str, api_key: str | None = None) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @abc.abstractmethod
    async def generate(self, req: GenerateRequest) -> GenerateResponse:
        """Send a completion request and return the response."""

    @abc.abstractmethod
    async def is_model_loaded(self, model: str) -> bool:
        """Check if a model is currently loaded / available."""

    @abc.abstractmethod
    async def load_model(self, model: str) -> None:
        """Ensure a model is loaded and ready for inference."""

    @abc.abstractmethod
    async def unload_model(self, model: str) -> None:
        """Release a model from memory (no-op for API providers)."""

    @property
    @abc.abstractmethod
    def is_local(self) -> bool:
        """True if this provider runs models locally (affects VRAM accounting)."""

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        """Return available model names."""

    async def model_vram_gb(self, model: str) -> float:
        """Estimated VRAM usage in GB. Override for local providers."""
        return 0.0
