# goose-orchestrator

A multi-model orchestrator-worker [MCP](https://modelcontextprotocol.io/) extension for [Goose](https://github.com/block/goose). Routes prompts to specialized worker models with VRAM-aware hot-swapping — only the orchestrator and active worker are loaded at any time.

## Features

- **Automatic task routing** — orchestrator LLM decomposes prompts into a dependency graph of sub-tasks, each assigned to a specialized worker role
- **VRAM-aware model pool** — LRU eviction ensures local models stay within a configurable memory budget; API models bypass the pool
- **Speculative preloading** — the router predicts the next worker needed and begins loading it during the current step
- **Parallel execution** — independent steps run concurrently up to a configurable worker limit
- **Per-worker temperature** — each role has its own sampling temperature (e.g. 0.1 for math, 0.9 for creative)
- **Goose-native configuration** — all settings managed through MCP tools in Goose's chat UI
- **Multi-provider** — supports Ollama (local), OpenAI-compatible APIs, and Anthropic

## Default Worker Roles

| Role | Default Model | Temperature | Optimized For |
|------|--------------|-------------|---------------|
| `deep_research` | `qwen3:32b` | 0.4 | Multi-hop web research, paper analysis |
| `local_rag` | `qwen3:8b` | 0.2 | Local document retrieval, code search |
| `code_gen` | `qwen2.5-coder:32b` | 0.3 | Code generation, refactoring, debugging |
| `summarizer` | `qwen3:8b` | 0.5 | Condensing outputs, report writing |
| `math_reasoning` | `qwen3:32b` | 0.1 | Formal proofs, calculations, logic |
| `creative` | `llama3:70b` | 0.9 | Creative writing, brainstorming |

All roles are fully customizable — change models, add new roles, or remove existing ones.

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- [Ollama](https://ollama.ai/) (for local models) and/or API keys for OpenAI/Anthropic

### Installation

Clone the repo and install:

```bash
git clone https://github.com/santiagoaraoz/goose-orchestrator.git
cd goose-orchestrator
uv sync
```

### Goose Integration (STDIO)

Add to `~/.config/goose/config.yaml`:

```yaml
extensions:
  multi_model_orchestrator:
    enabled: true
    type: stdio
    name: Multi-Model Orchestrator
    cmd: uv
    args:
      - run
      - --project
      - /path/to/goose-orchestrator
      - goose-orchestrator
    timeout: 600
```

Restart Goose to load the extension.

## Available Tools

### Core

| Tool | Description |
|------|-------------|
| `orchestrate(prompt)` | Route a prompt through the full orchestrator-worker pipeline |
| `status()` | Show loaded models, VRAM usage, and current configuration |
| `reset_workers()` | Unload all worker models from VRAM |

### Configuration

| Tool | Description |
|------|-------------|
| `list_config()` | Display full configuration as YAML |
| `configure_orchestrator(model, provider, context_window, endpoint)` | Update orchestrator model settings |
| `configure_worker(role, model, provider, context_window, temperature, enabled, description)` | Update or create a worker role |
| `remove_worker(role)` | Delete a worker role |
| `set_max_workers(count)` | Set max simultaneous workers (1-8) |
| `set_vram_budget(gb)` | Set total VRAM budget for local models |
| `configure_provider(name, endpoint, api_key_env)` | Configure a provider endpoint |

## Architecture

```
User Prompt → Orchestrator LLM (task classification)
                    ↓
            Task Plan (dependency graph)
                    ↓
        ┌───────────┼───────────┐
        ↓           ↓           ↓
   Worker A    Worker B    Worker C    (parallel where independent)
        ↓           ↓           ↓
        └───────────┼───────────┘
                    ↓
           Assembled Response
```

The **Model Pool** enforces a strict VRAM budget:
- Orchestrator model is pinned (never evicted)
- Worker models are evicted LRU-first when space is needed
- API-backed models have zero local VRAM cost

## Local Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Run the MCP server directly
uv run goose-orchestrator
```

## Testing

```bash
uv run pytest tests/ -v
```

Uses the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) for integration testing:

```bash
npx @modelcontextprotocol/inspector uv run goose-orchestrator
```

## License

[MIT](LICENSE)
