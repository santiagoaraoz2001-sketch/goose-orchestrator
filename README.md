# opencode-orchestrator

A multi-model orchestrator-worker [MCP](https://modelcontextprotocol.io/) extension for [Goose](https://github.com/block/goose) with a browser-based dashboard. Routes prompts to specialized worker models with VRAM-aware hot-swapping.

**by Specific Labs**

## Features

- **Automatic task routing** — orchestrator LLM decomposes prompts into a dependency graph of sub-tasks, each assigned to a specialized worker role
- **Specialized workers** — each role runs with its own model, temperature, and context window
- **VRAM-aware model pool** — LRU eviction ensures local models stay within a configurable memory budget; API models bypass the pool
- **Speculative preloading** — the router predicts the next worker needed and begins loading it during the current step
- **Parallel execution** — independent steps run concurrently up to a configurable worker limit
- **Browser dashboard** — full React UI with Blueprint design system (dark theme, live execution monitoring, config management)
- **macOS .app launcher** — double-click to start the server and open the UI
- **Multi-provider** — supports Ollama (local), OpenAI-compatible APIs, and Anthropic
- **OpenCode MCP integration** — also works as a native Goose extension via MCP tools

## Default Worker Roles

| Role | Default Model | Temp | Optimized For |
|------|--------------|------|---------------|
| `deep_research` | `qwen3:32b` | 0.4 | Multi-hop web research, paper analysis |
| `local_rag` | `qwen3:8b` | 0.2 | Local document retrieval, code search |
| `code_gen` | `qwen2.5-coder:32b` | 0.3 | Code generation, refactoring, debugging |
| `summarizer` | `qwen3:8b` | 0.5 | Condensing outputs, report writing |
| `math_reasoning` | `qwen3:32b` | 0.1 | Formal proofs, calculations, logic |
| `creative` | `llama3:70b` | 0.9 | Creative writing, brainstorming |

All roles are fully customizable via the UI or MCP tools.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 18+ (for frontend build)
- [Ollama](https://ollama.ai/) and/or API keys for OpenAI/Anthropic

### Install & Run (Browser UI)

```bash
git clone https://github.com/santiagoaraoz2001-sketch/opencode-orchestrator.git
cd opencode-orchestrator

# Build everything
uv sync
cd frontend && npm install && npm run build && cd ..

# Launch (opens browser to http://localhost:7432)
uv run opencode-orchestrator-ui
```

### macOS App (one-click launcher)

```bash
bash build-app.sh
cp -r "dist/OpenCode Orchestrator.app" /Applications/
```

Then launch from Spotlight or your Applications folder.

### OpenCode MCP Extension

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
      - /path/to/opencode-orchestrator
      - opencode-orchestrator
    timeout: 600
```

## Architecture

```
User Prompt → Orchestrator LLM (task classification)
                    ↓
            Task Plan (dependency graph)
                    ↓
        ┌───────────┼───────────┐
        ↓           ↓           ↓
    Worker A      Worker B      Worker C      (parallel)
   (research)    (code_gen)    (summarizer)
        ↓           ↓           ↓
        └───────────┼───────────┘
                    ↓
           Assembled Response
```

The **Model Pool** enforces a strict VRAM budget with LRU eviction. The orchestrator model is pinned and never evicted. API-backed models have zero local VRAM cost.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config` | Full configuration |
| `PATCH` | `/api/config/orchestrator` | Update orchestrator model |
| `GET` | `/api/config/workers` | List all worker roles |
| `PATCH` | `/api/config/workers/{role}` | Update a worker role |
| `POST` | `/api/config/workers/{role}` | Create a worker role |
| `DELETE` | `/api/config/workers/{role}` | Remove a worker role |
| `PATCH` | `/api/config/resources` | Update resource limits |
| `GET` | `/api/status` | Model pool status |
| `POST` | `/api/orchestrate` | Run orchestration (REST) |
| `WS` | `/api/ws` | Live execution streaming |
| `GET` | `/api/models/{provider}` | List available models |

## Development

```bash
# Backend (hot-reload)
uv run uvicorn opencode_orchestrator.backend.app:app --reload --port 7432

# Frontend (Vite dev server with proxy)
cd frontend && npm run dev

# Tests
uv run --extra dev pytest tests/ -v
```

## License

[MIT](LICENSE)
