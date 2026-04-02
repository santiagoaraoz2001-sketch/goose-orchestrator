"""FastAPI backend — serves the React SPA and exposes REST + WebSocket APIs."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from opencode_orchestrator.config_manager import ConfigManager
from opencode_orchestrator.orchestrator import Orchestrator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="OpenCode Orchestrator", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:7432", "http://127.0.0.1:7432"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ─────────────────────────────────────────────────────────

class OrchestratorUpdate(BaseModel):
    model: str | None = None
    provider: str | None = None
    context_window: int | None = None
    endpoint: str | None = None

class WorkerUpdate(BaseModel):
    model: str | None = None
    provider: str | None = None
    context_window: int | None = None
    temperature: float | None = None
    enabled: bool | None = None
    description: str | None = None

class WorkerCreate(BaseModel):
    model: str = "qwen3:8b"
    provider: str = "ollama"
    context_window: int = 16384
    temperature: float = 0.7
    enabled: bool = True
    description: str = ""
    tools: list[str] = []

class ResourceUpdate(BaseModel):
    max_simultaneous_workers: int | None = None
    vram_budget_gb: int | None = None
    api_rate_limit_rpm: int | None = None

class ProviderUpdate(BaseModel):
    endpoint: str | None = None
    api_key_env: str | None = None

class PromptRequest(BaseModel):
    prompt: str


# ── Config endpoints ─────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    cfg = ConfigManager()
    return JSONResponse(cfg.raw)


@app.patch("/api/config/orchestrator")
async def update_orchestrator(body: OrchestratorUpdate):
    cfg = ConfigManager()
    raw = cfg.raw
    for field in ["model", "provider", "context_window", "endpoint"]:
        val = getattr(body, field)
        if val is not None:
            raw["orchestrator"][field] = val
    cfg.update_raw(raw)
    return JSONResponse(cfg.raw["orchestrator"])


@app.get("/api/config/workers")
async def get_workers():
    cfg = ConfigManager()
    return JSONResponse(cfg.raw.get("workers", {}))


@app.patch("/api/config/workers/{role}")
async def update_worker(role: str, body: WorkerUpdate):
    cfg = ConfigManager()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return JSONResponse({"error": "No fields to update"}, status_code=400)
    cfg.update_worker(role, **updates)
    return JSONResponse(cfg.raw["workers"].get(role, {}))


@app.post("/api/config/workers/{role}")
async def create_worker(role: str, body: WorkerCreate):
    cfg = ConfigManager()
    if cfg.get_worker(role) is not None:
        return JSONResponse({"error": f"Role '{role}' already exists"}, status_code=409)
    cfg.update_worker(role, **body.model_dump())
    return JSONResponse(cfg.raw["workers"][role], status_code=201)


@app.delete("/api/config/workers/{role}")
async def delete_worker(role: str):
    cfg = ConfigManager()
    if cfg.get_worker(role) is None:
        return JSONResponse({"error": f"Role '{role}' not found"}, status_code=404)
    cfg.remove_worker(role)
    return JSONResponse({"deleted": role})


@app.patch("/api/config/resources")
async def update_resources(body: ResourceUpdate):
    cfg = ConfigManager()
    raw = cfg.raw
    raw.setdefault("resources", {})
    for field in ["max_simultaneous_workers", "vram_budget_gb", "api_rate_limit_rpm"]:
        val = getattr(body, field)
        if val is not None:
            raw["resources"][field] = val
    cfg.update_raw(raw)
    return JSONResponse(cfg.raw.get("resources", {}))


@app.patch("/api/config/providers/{name}")
async def update_provider(name: str, body: ProviderUpdate):
    cfg = ConfigManager()
    raw = cfg.raw
    raw.setdefault("providers", {}).setdefault(name, {})
    if body.endpoint is not None:
        raw["providers"][name]["endpoint"] = body.endpoint
    if body.api_key_env is not None:
        raw["providers"][name]["api_key_env"] = body.api_key_env
    cfg.update_raw(raw)
    return JSONResponse(raw["providers"][name])


# ── Status endpoints ─────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    orch = Orchestrator()
    return JSONResponse(orch.pool_status())


@app.post("/api/reset")
async def reset_workers():
    orch = Orchestrator()
    msg = await orch.reset()
    return JSONResponse({"message": msg})


# ── Model listing ────────────────────────────────────────────────────────────

@app.get("/api/models/{provider}")
async def list_models(provider: str):
    import os
    from opencode_orchestrator.providers import create_provider
    cfg = ConfigManager()
    ep = cfg.provider_endpoint(provider)
    endpoint = ep.endpoint if ep else ""
    api_key = None
    if ep and ep.api_key_env:
        api_key = os.environ.get(ep.api_key_env)
    try:
        prov = create_provider(provider, endpoint, api_key)
        models = await prov.list_models()
        return JSONResponse({"models": models})
    except Exception as e:
        return JSONResponse({"models": [], "error": str(e)})


@app.get("/api/models/discover/all")
async def discover_all_models():
    """Return rich metadata for every available model across all providers."""
    import os
    from opencode_orchestrator.providers import create_provider
    cfg = ConfigManager()
    results: list[dict] = []

    # Ollama — fetch detailed metadata from /api/tags
    ep = cfg.provider_endpoint("ollama")
    ollama_endpoint = (ep.endpoint if ep else "http://localhost:11434").rstrip("/")
    try:
        import requests as _req
        resp = _req.get(f"{ollama_endpoint}/api/tags", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Also fetch currently running models
        ps_resp = _req.get(f"{ollama_endpoint}/api/ps", timeout=10)
        running_names: set[str] = set()
        if ps_resp.ok:
            for m in ps_resp.json().get("models", []):
                running_names.add(m.get("name", ""))

        for m in data.get("models", []):
            details = m.get("details", {})
            size_bytes = m.get("size", 0)
            size_gb = round(size_bytes / (1024 ** 3), 1)
            results.append({
                "name": m["name"],
                "provider": "ollama",
                "family": details.get("family", "unknown"),
                "parameter_size": details.get("parameter_size", ""),
                "quantization": details.get("quantization_level", ""),
                "size_gb": size_gb,
                "modified_at": m.get("modified_at", ""),
                "format": details.get("format", ""),
                "loaded": m["name"] in running_names,
            })
    except Exception as e:
        log.warning("Ollama discovery failed: %s", e)

    # OpenAI / Anthropic — add static model lists
    for prov_name in ["openai", "anthropic"]:
        prov_ep = cfg.provider_endpoint(prov_name)
        if not prov_ep:
            continue
        api_key = None
        if prov_ep.api_key_env:
            api_key = os.environ.get(prov_ep.api_key_env)
        try:
            prov = create_provider(prov_name, prov_ep.endpoint, api_key)
            model_names = await prov.list_models()
            for name in model_names:
                results.append({
                    "name": name,
                    "provider": prov_name,
                    "family": prov_name,
                    "parameter_size": "",
                    "quantization": "",
                    "size_gb": 0,
                    "modified_at": "",
                    "format": "api",
                    "loaded": True,  # API models are always "available"
                })
        except Exception:
            pass

    # Include current assignment info
    orch_model = cfg.cfg.orchestrator.model
    worker_assignments: dict[str, list[str]] = {}
    for role, wcfg in cfg.cfg.workers.items():
        worker_assignments.setdefault(wcfg.model, []).append(role)

    for r in results:
        r["is_orchestrator"] = r["name"] == orch_model
        r["assigned_roles"] = worker_assignments.get(r["name"], [])

    return JSONResponse({"models": results})


@app.post("/api/models/assign")
async def assign_model(body: dict):
    """Assign a model to the orchestrator or a worker role."""
    target = body.get("target")  # "orchestrator" or role name
    model = body.get("model")
    provider = body.get("provider", "ollama")

    if not target or not model:
        return JSONResponse({"error": "target and model required"}, status_code=400)

    cfg = ConfigManager()
    raw = cfg.raw

    if target == "orchestrator":
        raw["orchestrator"]["model"] = model
        raw["orchestrator"]["provider"] = provider
        cfg.update_raw(raw)
        return JSONResponse({"message": f"Orchestrator model set to {model}"})
    else:
        # Assign to worker role
        if target not in raw.get("workers", {}):
            return JSONResponse({"error": f"Worker role '{target}' not found"}, status_code=404)
        raw["workers"][target]["model"] = model
        raw["workers"][target]["provider"] = provider
        cfg.update_raw(raw)
        return JSONResponse({"message": f"Worker '{target}' model set to {model}"})


# ── Orchestration (REST) ─────────────────────────────────────────────────────

@app.post("/api/orchestrate")
async def orchestrate(body: PromptRequest):
    orch = Orchestrator()
    try:
        result = await orch.run(body.prompt)
        return JSONResponse({"result": result})
    except Exception as e:
        log.exception("Orchestration failed")
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Orchestration (WebSocket — live streaming) ───────────────────────────────

@app.websocket("/api/ws")
async def ws_orchestrate(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "orchestrate":
                prompt = msg.get("prompt", "")
                orch = Orchestrator()
                async for event in orch.run_with_events(prompt):
                    await ws.send_text(json.dumps(event))
            elif msg.get("type") == "status":
                orch = Orchestrator()
                await ws.send_text(json.dumps({"type": "status_response", **orch.pool_status()}))
            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    except Exception as e:
        log.error("WebSocket error: %s", e)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


# ── SPA static files ─────────────────────────────────────────────────────────

def _find_frontend_dist() -> Path | None:
    """Locate the built frontend dist directory."""
    candidates = [
        Path(__file__).resolve().parents[3] / "frontend" / "dist",   # dev: repo root
        Path(__file__).resolve().parent / "frontend_dist",            # installed package
    ]
    for p in candidates:
        if p.is_dir() and (p / "index.html").exists():
            return p
    return None


_dist = _find_frontend_dist()
if _dist:
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # SPA catch-all: return index.html for all non-API routes
    @app.get("/{path:path}")
    async def spa_catchall(path: str):
        file_path = _dist / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_dist / "index.html"))
else:
    @app.get("/")
    async def no_frontend():
        return JSONResponse({
            "message": "Frontend not built. Run: cd frontend && npm install && npm run build",
            "api_docs": "/docs",
        })


# ── Entry point ──────────────────────────────────────────────────────────────

def start():
    """CLI entry point for opencode-orchestrator-ui."""
    import argparse
    parser = argparse.ArgumentParser(description="OpenCode Orchestrator Web UI")
    parser.add_argument("--port", type=int, default=7432, help="Port (default: 7432)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host")
    parser.add_argument("--no-open", action="store_true", default=False, help="Don't open browser")
    args = parser.parse_args()

    if not args.no_open:
        import webbrowser
        import threading
        def _open():
            import time; time.sleep(1.5)
            webbrowser.open(f"http://localhost:{args.port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    start()
