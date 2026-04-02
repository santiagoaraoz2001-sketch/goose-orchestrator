"""Built-in tools available to worker roles: SearXNG web search, Ollama embeddings."""

from __future__ import annotations

import asyncio
import logging
from functools import partial

import requests

from goose_orchestrator.config_manager import ConfigManager

log = logging.getLogger(__name__)


# =============================================================================
# SearXNG Web Search
# =============================================================================

async def searxng_search(query: str, max_results: int = 10) -> str:
    """Search the web via SearXNG and return formatted results.

    Returns a markdown-formatted list of results with title, URL, and snippet.
    """
    cfg = ConfigManager()
    searxng_url = cfg.raw.get("searxng", {}).get("endpoint", "http://localhost:8888")

    loop = asyncio.get_event_loop()

    def _do():
        resp = requests.get(
            f"{searxng_url}/search",
            params={"q": query, "format": "json"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        data = await loop.run_in_executor(None, _do)
        results = data.get("results", [])[:max_results]

        if not results:
            return f"No search results found for: {query}"

        lines = [f"## Search Results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            snippet = r.get("content", "")[:200]
            lines.append(f"**{i}. {title}**\n{url}\n{snippet}\n")

        return "\n".join(lines)

    except Exception as e:
        log.error("SearXNG search failed: %s", e)
        return f"Search failed: {e}"


async def searxng_fetch_url(url: str) -> str:
    """Fetch a URL's text content (via requests, not a browser)."""
    loop = asyncio.get_event_loop()

    def _do():
        resp = requests.get(url, timeout=30, headers={"User-Agent": "GooseOrchestrator/0.2"})
        resp.raise_for_status()
        return resp.text[:10000]  # Cap at 10k chars

    try:
        text = await loop.run_in_executor(None, _do)
        return f"## Content from {url}\n\n{text}"
    except Exception as e:
        return f"Failed to fetch {url}: {e}"


# =============================================================================
# Ollama Embeddings
# =============================================================================

async def ollama_embed(text: str, model: str | None = None) -> list[float]:
    """Generate embeddings for text using Ollama.

    Returns the embedding vector as a list of floats.
    """
    cfg = ConfigManager()
    endpoint = cfg.raw.get("providers", {}).get("ollama", {}).get("endpoint", "http://localhost:11434")
    embed_model = model or cfg.raw.get("embedding", {}).get("model", "nomic-embed-text:latest")

    loop = asyncio.get_event_loop()

    def _do():
        resp = requests.post(
            f"{endpoint}/api/embed",
            json={"model": embed_model, "input": text},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()

    data = await loop.run_in_executor(None, _do)
    embeddings = data.get("embeddings", [[]])[0]
    return embeddings


async def embed_and_rank(query: str, documents: list[str], model: str | None = None, top_k: int = 5) -> str:
    """Embed a query and a list of documents, return the top-k most similar.

    Uses cosine similarity to rank documents against the query.
    Returns a formatted string with the top matches.
    """
    import math

    def cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    query_emb = await ollama_embed(query, model)
    if not query_emb:
        return "Failed to generate query embedding"

    scored: list[tuple[float, int, str]] = []
    for i, doc in enumerate(documents):
        doc_emb = await ollama_embed(doc, model)
        if doc_emb:
            sim = cosine_sim(query_emb, doc_emb)
            scored.append((sim, i, doc))

    scored.sort(key=lambda x: -x[0])
    top = scored[:top_k]

    lines = [f"## Top {len(top)} results for: {query}\n"]
    for sim, idx, doc in top:
        preview = doc[:300].replace("\n", " ")
        lines.append(f"**[{sim:.3f}]** {preview}...\n")

    return "\n".join(lines)


# =============================================================================
# Tool registry — maps tool names to functions
# =============================================================================

TOOL_REGISTRY: dict[str, callable] = {
    "web_search": searxng_search,
    "url_fetch": searxng_fetch_url,
    "embed_and_rank": embed_and_rank,
}
