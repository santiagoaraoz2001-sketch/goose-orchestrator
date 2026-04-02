"""FastMCP server — exposes orchestrator tools to Goose.

All configuration is done through MCP tools that Goose renders natively in its UI,
rather than through a separate Gradio/web interface.
"""

from __future__ import annotations

import json
import logging

from mcp.server.fastmcp import FastMCP

from goose_orchestrator.config_manager import ConfigManager
from goose_orchestrator.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

mcp = FastMCP("goose-orchestrator")

# =============================================================================
# System-level instruction resource — Goose reads this to understand the tool
# =============================================================================

SYSTEM_INSTRUCTIONS = """\
# Goose Orchestrator — Multi-Model Agent Extension

You have access to the **goose-orchestrator** extension, which lets you decompose \
complex tasks into sub-tasks and route each to a specialized worker model. \
This is useful when a single model isn't optimal for every part of a request — e.g. \
research requires a different model than code generation or mathematical reasoning.

## When to use `orchestrate`

Use the `orchestrate` tool when the user's request involves **two or more distinct \
cognitive tasks** that would benefit from different model specializations. Examples:

- "Research X, then write code implementing it" → deep_research + code_gen
- "Analyze this data and write a creative summary" → math_reasoning + creative
- "Find papers on Y, extract key findings, then produce a report" → deep_research + summarizer
- "Debug this code and explain the fix simply" → code_gen + summarizer

Do NOT use `orchestrate` for simple, single-domain requests that you can handle \
directly (e.g. "fix this typo", "what is 2+2", "write a haiku").

## Available worker roles (default)

| Role | Specialization | Default temp |
|------|---------------|-------------|
| `deep_research` | Multi-hop web research, paper analysis, citation chains | 0.4 |
| `local_rag` | Local document retrieval, codebase search, file Q&A | 0.2 |
| `code_gen` | Code generation, refactoring, debugging, test writing | 0.3 |
| `summarizer` | Condensing large outputs, report writing, key point extraction | 0.5 |
| `math_reasoning` | Formal proofs, calculations, step-by-step logical reasoning | 0.1 |
| `creative` | Creative writing, brainstorming, ideation, storytelling | 0.9 |

The user can add, remove, or reconfigure roles. Use `status` to see current config.

## Configuration workflow

When the user wants to visually configure models, roles, or settings:

1. **Use `open_dashboard`** — this launches the browser UI with model dropdowns, \
   role cards, temperature sliders, and VRAM monitoring. This is the PREFERRED way \
   for users to configure the orchestrator.

For quick chat-based changes (no UI needed):

1. Use `status` to show current config (which models are assigned to which roles)
2. Use `configure_worker` to change a role's model, provider, temperature, or context window
3. Use `configure_orchestrator` to change the planning model itself
4. Use `set_max_workers` to control parallelism (higher = more VRAM usage)
5. Use `set_vram_budget` to set the memory ceiling for local models

## Model provider details

- **ollama**: Local models. The pool loads/unloads them from VRAM using Ollama's \
  keep_alive API. Only the orchestrator + active worker(s) are loaded at any time.
- **openai**: API-based (OpenAI, vLLM, LM Studio). Zero VRAM cost. Always available.
- **anthropic**: API-based (Claude models). Zero VRAM cost. Always available.

## VRAM management

The system enforces a strict VRAM budget. When a new worker model needs to load \
and VRAM is full, the least-recently-used worker model is evicted first. The \
orchestrator model is pinned and never evicted. API-backed models skip the pool \
entirely. Use `reset_workers` to free all VRAM except the orchestrator.

## Web UI

The extension also provides a browser dashboard at http://localhost:7432 (launched \
via `goose-orchestrator-ui`). The user can configure everything from either the \
chat tools or the web UI — they share the same config file.

## Important notes

- Always call `status` first if the user asks about current configuration
- The orchestrator model does the planning; worker models do the execution
- Temperature is per-role: low for precision tasks, high for creative tasks
- Context window limits how many tokens each worker can generate per step
- If orchestration fails (e.g. Ollama not running), report the error clearly
"""


@mcp.resource("goose://orchestrator/instructions")
def get_instructions() -> str:
    """System instructions for how the LLM should use this extension."""
    return SYSTEM_INSTRUCTIONS


# =============================================================================
# UI launcher
# =============================================================================

@mcp.tool()
async def open_dashboard() -> str:
    """Open the orchestrator dashboard in the browser.

    Launches the web UI at http://localhost:7432 where you can:
    - See all worker roles with their assigned models
    - Change models for each role via dropdown (auto-populated from Ollama)
    - Adjust temperature, context window, and enable/disable per role
    - Configure the orchestrator model and provider
    - Monitor VRAM usage and loaded models
    - Run orchestration tasks with live streaming output

    Call this whenever the user wants to configure models, view roles,
    or manage the orchestrator visually.
    """
    import subprocess
    import threading
    import time

    def _start():
        try:
            subprocess.Popen(
                ["uv", "run", "--project",
                 str(__import__("pathlib").Path(__file__).resolve().parents[2]),
                 "goose-orchestrator-ui", "--port", "7432"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            import webbrowser
            webbrowser.open("http://localhost:7432")
        except Exception:
            pass

    # Check if already running
    import requests
    try:
        requests.get("http://127.0.0.1:7432/api/status", timeout=1)
        import webbrowser
        webbrowser.open("http://localhost:7432")
        return "Dashboard already running — opened http://localhost:7432 in your browser."
    except Exception:
        threading.Thread(target=_start, daemon=True).start()
        return (
            "Starting dashboard server... Opening http://localhost:7432 in your browser.\n\n"
            "The dashboard lets you:\n"
            "- **Models page**: Select models for each worker role via dropdown\n"
            "- **Workers page**: Add/remove roles, adjust temperature & context\n"
            "- **Settings page**: Configure orchestrator model & resource limits\n"
            "- **Status page**: Monitor VRAM usage and loaded models\n"
            "- **Dashboard**: Run orchestration tasks with live output"
        )


# =============================================================================
# Core orchestration tools
# =============================================================================

@mcp.tool()
async def orchestrate(prompt: str) -> str:
    """IMPORTANT: Use this tool for ANY request that involves research, multi-step analysis,
    or combining different skills (research + code, research + summarization, etc.).

    This tool decomposes the prompt into sub-tasks and routes each to a specialized
    worker model running on Ollama. It has access to:
    - SearXNG web search (for deep_research tasks)
    - Ollama embedding models (for local_rag tasks)
    - Code-specialized models (for code_gen tasks)
    - Math/reasoning models (for math_reasoning tasks)
    - Summarization models (for summarizer tasks)
    - Creative writing models (for creative tasks)

    ALWAYS use this instead of trying to do research, web scraping, or multi-step
    tasks yourself. This tool has its own SearXNG search engine and specialized models.

    Examples of when to use this tool:
    - "Research X and summarize" -> USE THIS TOOL
    - "Find papers on X, then write code for it" -> USE THIS TOOL
    - "Analyze X and write a creative summary" -> USE THIS TOOL

    Args:
        prompt: The full user request to decompose and execute.
    """
    orch = Orchestrator()
    return await orch.run(prompt)


@mcp.tool()
async def orchestrator_status() -> str:
    """Show the Multi-Model Orchestrator status: loaded models, VRAM, and worker role config.

    Use this when the user asks about orchestrator status, what models are assigned
    to what roles, or wants to see the current configuration.
    """
    orch = Orchestrator()
    pool = orch.pool_status()
    cfg = ConfigManager()

    lines: list[str] = []
    lines.append("## Model Pool Status")
    lines.append(f"- **VRAM Budget**: {pool['vram_budget_gb']} GB")
    lines.append(f"- **Used**: {pool['used_vram_gb']} GB")
    lines.append(f"- **Available**: {pool['available_vram_gb']} GB")
    lines.append("")

    if pool["loaded_models"]:
        lines.append("### Loaded Models")
        for m in pool["loaded_models"]:
            tag = " (orchestrator)" if m["is_orchestrator"] else ""
            lines.append(
                f"- **{m['model']}** [{m['provider']}] — "
                f"{m['vram_gb']} GB, idle {m['idle_seconds']}s{tag}"
            )
    else:
        lines.append("*No models currently loaded*")

    lines.append("")
    lines.append("## Worker Configuration")
    lines.append(f"- **Orchestrator model**: {cfg.cfg.orchestrator.model} "
                 f"({cfg.cfg.orchestrator.provider})")
    lines.append(f"- **Max simultaneous workers**: {cfg.cfg.resources.max_simultaneous_workers}")
    lines.append("")

    for role, wcfg in cfg.cfg.workers.items():
        enabled = "enabled" if wcfg.enabled else "disabled"
        lines.append(
            f"- **{role}**: {wcfg.model} ({wcfg.provider}) | "
            f"ctx={wcfg.context_window} | temp={wcfg.temperature} | {enabled}"
        )

    return "\n".join(lines)


@mcp.tool()
async def reset_workers() -> str:
    """Unload all worker models from VRAM, keeping only the orchestrator.

    Use this to free memory when switching tasks or if VRAM is running low.
    """
    orch = Orchestrator()
    return await orch.reset()


# =============================================================================
# Configuration tools (Goose-native UI)
# =============================================================================

@mcp.tool()
async def list_config() -> str:
    """Show the full orchestrator configuration as YAML.

    Displays all settings: orchestrator model, worker roles (model, provider,
    context window, temperature, enabled state), resource limits, and provider
    endpoints.
    """
    import yaml
    cfg = ConfigManager()
    return f"```yaml\n{yaml.dump(cfg.raw, default_flow_style=False, sort_keys=False)}```"


@mcp.tool()
async def configure_orchestrator(
    model: str | None = None,
    provider: str | None = None,
    context_window: int | None = None,
    endpoint: str | None = None,
) -> str:
    """Update the orchestrator model settings.

    Args:
        model: Model name (e.g. "qwen3:14b", "claude-sonnet-4-6").
        provider: Provider backend ("ollama", "openai", "anthropic").
        context_window: Max context window in tokens.
        endpoint: Provider API endpoint URL.
    """
    cfg = ConfigManager()
    raw = cfg.raw

    if model is not None:
        raw["orchestrator"]["model"] = model
    if provider is not None:
        raw["orchestrator"]["provider"] = provider
    if context_window is not None:
        raw["orchestrator"]["context_window"] = context_window
    if endpoint is not None:
        raw["orchestrator"]["endpoint"] = endpoint

    cfg.update_raw(raw)

    orch_cfg = cfg.cfg.orchestrator
    return (
        f"Orchestrator updated:\n"
        f"- Model: {orch_cfg.model}\n"
        f"- Provider: {orch_cfg.provider}\n"
        f"- Context window: {orch_cfg.context_window}\n"
        f"- Endpoint: {orch_cfg.endpoint}"
    )


@mcp.tool()
async def configure_worker(
    role: str,
    model: str | None = None,
    provider: str | None = None,
    context_window: int | None = None,
    temperature: float | None = None,
    enabled: bool | None = None,
    description: str | None = None,
) -> str:
    """Update a worker role's settings. Creates the role if it doesn't exist.

    Args:
        role: Role name (e.g. "deep_research", "code_gen", "summarizer").
        model: Model name to use for this role.
        provider: Provider backend ("ollama", "openai", "anthropic").
        context_window: Max context window in tokens for this worker.
        temperature: Sampling temperature (0.0=deterministic, 1.0=creative).
        enabled: Whether this worker role is available for task routing.
        description: Human-readable description of what this role does
                     (helps the orchestrator decide when to use it).
    """
    cfg = ConfigManager()
    updates: dict = {}
    if model is not None:
        updates["model"] = model
    if provider is not None:
        updates["provider"] = provider
    if context_window is not None:
        updates["context_window"] = context_window
    if temperature is not None:
        updates["temperature"] = temperature
    if enabled is not None:
        updates["enabled"] = enabled
    if description is not None:
        updates["description"] = description

    # If creating a new role, ensure required fields have defaults
    existing = cfg.get_worker(role)
    if existing is None:
        updates.setdefault("model", "qwen3:8b")
        updates.setdefault("provider", "ollama")
        updates.setdefault("context_window", 16384)
        updates.setdefault("temperature", 0.7)
        updates.setdefault("enabled", True)
        updates.setdefault("description", f"Custom worker role: {role}")
        updates.setdefault("tools", [])

    cfg.update_worker(role, **updates)
    wcfg = cfg.get_worker(role)

    return (
        f"Worker **{role}** updated:\n"
        f"- Model: {wcfg.model}\n"
        f"- Provider: {wcfg.provider}\n"
        f"- Context window: {wcfg.context_window}\n"
        f"- Temperature: {wcfg.temperature}\n"
        f"- Enabled: {wcfg.enabled}\n"
        f"- Description: {wcfg.description}"
    )


@mcp.tool()
async def remove_worker(role: str) -> str:
    """Remove a worker role entirely from the configuration.

    Args:
        role: The role name to remove (e.g. "creative", "math_reasoning").
    """
    cfg = ConfigManager()
    if cfg.get_worker(role) is None:
        return f"Role '{role}' does not exist."
    cfg.remove_worker(role)
    return f"Worker role '{role}' removed."


@mcp.tool()
async def set_max_workers(count: int) -> str:
    """Set the maximum number of worker models that can run simultaneously.

    Higher values enable more parallelism but consume more VRAM.
    Recommended: 1 for <64GB VRAM, 2 for 64-128GB, 3-4 for >128GB.

    Args:
        count: Maximum simultaneous workers (1-8).
    """
    if not 1 <= count <= 8:
        return "Error: count must be between 1 and 8."
    cfg = ConfigManager()
    raw = cfg.raw
    raw.setdefault("resources", {})["max_simultaneous_workers"] = count
    cfg.update_raw(raw)
    return f"Max simultaneous workers set to {count}."


@mcp.tool()
async def set_vram_budget(gb: int) -> str:
    """Set the total VRAM budget in GB for local model loading.

    The pool will evict models to stay within this budget.
    Set this to your total unified/GPU memory minus ~8GB for OS overhead.

    Args:
        gb: VRAM budget in gigabytes.
    """
    if gb < 4:
        return "Error: VRAM budget must be at least 4 GB."
    cfg = ConfigManager()
    raw = cfg.raw
    raw.setdefault("resources", {})["vram_budget_gb"] = gb
    cfg.update_raw(raw)
    return f"VRAM budget set to {gb} GB."


@mcp.tool()
async def configure_provider(
    name: str,
    endpoint: str | None = None,
    api_key_env: str | None = None,
) -> str:
    """Configure a provider endpoint (ollama, openai, anthropic, or custom).

    Args:
        name: Provider name (e.g. "ollama", "openai", "anthropic", or a custom name).
        endpoint: API endpoint URL.
        api_key_env: Environment variable name containing the API key.
    """
    cfg = ConfigManager()
    raw = cfg.raw
    raw.setdefault("providers", {}).setdefault(name, {})
    if endpoint is not None:
        raw["providers"][name]["endpoint"] = endpoint
    if api_key_env is not None:
        raw["providers"][name]["api_key_env"] = api_key_env
    cfg.update_raw(raw)
    return f"Provider '{name}' configured: endpoint={raw['providers'][name].get('endpoint', 'N/A')}"


# =============================================================================
# MCP Prompts (task templates)
# =============================================================================

@mcp.prompt()
def research_and_code(topic: str) -> str:
    """Template: research a topic then generate code based on findings."""
    return (
        f"Research the following topic thoroughly, then write production-quality "
        f"code implementing the key findings:\n\n{topic}"
    )


@mcp.prompt()
def analyze_and_summarize(content: str) -> str:
    """Template: analyze content with reasoning, then produce a concise summary."""
    return (
        f"First, analyze the following content using rigorous logical reasoning. "
        f"Then produce a concise executive summary:\n\n{content}"
    )
