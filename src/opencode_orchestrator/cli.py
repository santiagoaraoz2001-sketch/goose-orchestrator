"""CLI entry points — shell-callable orchestrator commands.

These exist so models that can't call MCP tools directly (e.g. local Ollama models
in OpenCode) can still invoke the orchestrator via Developer.shell / subprocess.

Usage:
    opencode-orchestrate "Research X, then summarize"
    opencode-orchestrate-status
    opencode-orchestrate-config
    opencode-orchestrate-configure-worker code_gen --model devstral-small-2:Q8_0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _run_async(coro):
    """Run an async function synchronously."""
    return asyncio.run(coro)


def cli_orchestrate():
    """CLI: run an orchestration task."""
    parser = argparse.ArgumentParser(description="Run multi-model orchestration")
    parser.add_argument("prompt", nargs="?", help="The prompt to orchestrate")
    parser.add_argument("--prompt-file", type=str, help="Read prompt from file")
    args = parser.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        with open(args.prompt_file) as f:
            prompt = f.read().strip()
    if not prompt:
        prompt = sys.stdin.read().strip()
    if not prompt:
        print("Error: no prompt provided", file=sys.stderr)
        sys.exit(1)

    from opencode_orchestrator.orchestrator import Orchestrator

    async def _run():
        orch = Orchestrator()
        result = await orch.run(prompt)
        print(result)

    _run_async(_run())


def cli_status():
    """CLI: show orchestrator status."""
    from opencode_orchestrator.config_manager import ConfigManager
    from opencode_orchestrator.orchestrator import Orchestrator

    async def _run():
        orch = Orchestrator()
        pool = orch.pool_status()
        cfg = ConfigManager()

        print("=== Model Pool ===")
        print(f"VRAM: {pool['used_vram_gb']}/{pool['vram_budget_gb']} GB used")
        print(f"Available: {pool['available_vram_gb']} GB")
        print()

        if pool["loaded_models"]:
            print("Loaded models:")
            for m in pool["loaded_models"]:
                tag = " (orchestrator)" if m["is_orchestrator"] else ""
                print(f"  {m['model']} [{m['provider']}] — {m['vram_gb']} GB{tag}")
        else:
            print("No models loaded")

        print()
        print("=== Worker Configuration ===")
        print(f"Orchestrator: {cfg.cfg.orchestrator.model} ({cfg.cfg.orchestrator.provider})")
        print(f"Max workers: {cfg.cfg.resources.max_simultaneous_workers}")
        print()

        for role, wcfg in cfg.cfg.workers.items():
            status = "ON" if wcfg.enabled else "OFF"
            print(f"  [{status}] {role}: {wcfg.model} ({wcfg.provider}) "
                  f"ctx={wcfg.context_window} temp={wcfg.temperature}")

    _run_async(_run())


def cli_config():
    """CLI: dump full config as YAML."""
    import yaml
    from opencode_orchestrator.config_manager import ConfigManager
    cfg = ConfigManager()
    print(yaml.dump(cfg.raw, default_flow_style=False, sort_keys=False))


def cli_configure_worker():
    """CLI: update a worker role's settings."""
    parser = argparse.ArgumentParser(description="Configure a worker role")
    parser.add_argument("role", help="Role name (e.g. code_gen, deep_research)")
    parser.add_argument("--model", type=str, help="Model name")
    parser.add_argument("--provider", type=str, help="Provider (ollama/openai/anthropic)")
    parser.add_argument("--context-window", type=int, help="Context window in tokens")
    parser.add_argument("--temperature", type=float, help="Sampling temperature")
    parser.add_argument("--enable", action="store_true", help="Enable role")
    parser.add_argument("--disable", action="store_true", help="Disable role")
    args = parser.parse_args()

    from opencode_orchestrator.config_manager import ConfigManager
    cfg = ConfigManager()

    updates = {}
    if args.model:
        updates["model"] = args.model
    if args.provider:
        updates["provider"] = args.provider
    if args.context_window:
        updates["context_window"] = args.context_window
    if args.temperature is not None:
        updates["temperature"] = args.temperature
    if args.enable:
        updates["enabled"] = True
    if args.disable:
        updates["enabled"] = False

    if not updates:
        # Just show current config for this role
        w = cfg.get_worker(args.role)
        if w:
            print(f"{args.role}:")
            print(f"  model: {w.model}")
            print(f"  provider: {w.provider}")
            print(f"  context_window: {w.context_window}")
            print(f"  temperature: {w.temperature}")
            print(f"  enabled: {w.enabled}")
            print(f"  description: {w.description}")
        else:
            print(f"Role '{args.role}' not found")
        return

    cfg.update_worker(args.role, **updates)
    w = cfg.get_worker(args.role)
    print(f"Updated {args.role}:")
    print(f"  model: {w.model}")
    print(f"  provider: {w.provider}")
    print(f"  context_window: {w.context_window}")
    print(f"  temperature: {w.temperature}")
    print(f"  enabled: {w.enabled}")
