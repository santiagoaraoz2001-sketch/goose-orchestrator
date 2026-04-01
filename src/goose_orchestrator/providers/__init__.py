"""LLM provider backends."""

from goose_orchestrator.providers.base import BaseProvider, GenerateRequest, GenerateResponse
from goose_orchestrator.providers.ollama_provider import OllamaProvider
from goose_orchestrator.providers.openai_provider import OpenAIProvider
from goose_orchestrator.providers.anthropic_provider import AnthropicProvider

PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def create_provider(name: str, endpoint: str, api_key: str | None = None) -> BaseProvider:
    cls = PROVIDER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(PROVIDER_REGISTRY)}")
    return cls(endpoint=endpoint, api_key=api_key)
