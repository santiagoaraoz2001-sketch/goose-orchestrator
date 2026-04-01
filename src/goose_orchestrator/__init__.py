"""Goose multi-model orchestrator-worker extension."""

import argparse

from goose_orchestrator.server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="Multi-model orchestrator-worker extension for Goose"
    )
    parser.add_argument("--config", type=str, default=None, help="Path to config YAML")
    args = parser.parse_args()

    if args.config:
        from goose_orchestrator.config_manager import ConfigManager
        ConfigManager.set_config_path(args.config)

    mcp.run()
