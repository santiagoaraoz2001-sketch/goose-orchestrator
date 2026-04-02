"""Task router — classifies prompts into a dependency graph of worker sub-tasks."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from opencode_orchestrator.config_manager import ConfigManager
from opencode_orchestrator.providers.base import BaseProvider, GenerateRequest

log = logging.getLogger(__name__)


@dataclass
class TaskStep:
    """A single step in the execution plan."""
    id: int
    role: str
    sub_prompt: str
    depends_on: list[int] = field(default_factory=list)
    context_budget: int = 8192
    preload_hint: str | None = None  # role to speculatively preload next


@dataclass
class TaskPlan:
    """Full execution plan produced by the orchestrator."""
    steps: list[TaskStep]
    summary: str = ""  # orchestrator's reasoning about the plan


ROUTER_SYSTEM_PROMPT = """\
You are a task planning orchestrator. Given a user prompt and a set of available \
worker roles, decompose the prompt into a dependency graph of sub-tasks.

Available worker roles:
{role_catalog}

Rules:
1. Each step must specify exactly one role from the available roles.
2. Steps with no dependencies can execute in parallel.
3. Use "depends_on" to express ordering constraints (list of step IDs).
4. Set "context_budget" to a GENEROUS token limit. Workers should have enough room to \
   produce thorough, complete responses. Use at least 8192 for research and code tasks, \
   and at least 4096 for summarization. Never set below 2048.
5. If you predict which role will be needed AFTER a step, set "preload_hint" to that role name \
   so the system can speculatively pre-load the model.
6. If the prompt is simple and only needs one role, return a single step.
7. NEVER invent roles that aren't in the catalog.

Respond with ONLY valid JSON matching this schema:
{{
  "summary": "brief reasoning about the plan",
  "steps": [
    {{
      "id": 1,
      "role": "role_name",
      "sub_prompt": "what to tell this worker",
      "depends_on": [],
      "context_budget": 8192,
      "preload_hint": "next_role_or_null"
    }}
  ]
}}
"""


def _build_role_catalog(cfg: ConfigManager) -> str:
    lines: list[str] = []
    for role, wcfg in cfg.enabled_workers().items():
        lines.append(f"- **{role}**: {wcfg.description} (model: {wcfg.model}, "
                      f"max context: {wcfg.context_window} tokens)")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM output that might contain markdown fences or preamble."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code fence
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    raise ValueError(f"Could not extract valid JSON from LLM output:\n{text[:500]}")


class TaskRouter:
    """Uses the orchestrator model to decompose prompts into task plans."""

    def __init__(self, provider: BaseProvider, model: str) -> None:
        self._provider = provider
        self._model = model

    async def plan(self, user_prompt: str) -> TaskPlan:
        cfg = ConfigManager()
        catalog = _build_role_catalog(cfg)
        system = ROUTER_SYSTEM_PROMPT.format(role_catalog=catalog)

        req = GenerateRequest(
            model=self._model,
            prompt=user_prompt,
            system=system,
            max_tokens=2048,
            temperature=0.3,  # low temp for structured planning
            json_mode=True,
        )

        log.info("Routing prompt: %.100s...", user_prompt)
        resp = await self._provider.generate(req)

        try:
            data = _extract_json(resp.text)
        except ValueError:
            log.warning("Router produced invalid JSON, falling back to single-step plan")
            return self._fallback_plan(user_prompt, cfg)

        return self._parse_plan(data, cfg)

    def _parse_plan(self, data: dict, cfg: ConfigManager) -> TaskPlan:
        steps: list[TaskStep] = []
        enabled_roles = set(cfg.enabled_workers().keys())

        for raw_step in data.get("steps", []):
            role = raw_step.get("role", "")
            if role not in enabled_roles:
                log.warning("Router assigned unknown/disabled role %r, skipping step", role)
                continue

            worker_cfg = cfg.get_worker(role)
            max_ctx = worker_cfg.context_window if worker_cfg else 8192
            raw_budget = raw_step.get("context_budget", 8192)
            budget = max(2048, min(raw_budget, max_ctx))  # floor at 2048, cap at context_window

            hint = raw_step.get("preload_hint")
            if hint and hint not in enabled_roles:
                hint = None

            steps.append(TaskStep(
                id=raw_step.get("id", len(steps) + 1),
                role=role,
                sub_prompt=raw_step.get("sub_prompt", ""),
                depends_on=raw_step.get("depends_on", []),
                context_budget=budget,
                preload_hint=hint,
            ))

        if not steps:
            log.warning("Router returned empty plan, falling back")
            return self._fallback_plan("", cfg)

        return TaskPlan(steps=steps, summary=data.get("summary", ""))

    def _fallback_plan(self, prompt: str, cfg: ConfigManager) -> TaskPlan:
        """Single-step plan using the first enabled worker."""
        enabled = cfg.enabled_workers()
        if not enabled:
            raise RuntimeError("No enabled workers configured")
        role = next(iter(enabled))
        return TaskPlan(
            steps=[TaskStep(id=1, role=role, sub_prompt=prompt)],
            summary="Fallback: single-step plan",
        )
