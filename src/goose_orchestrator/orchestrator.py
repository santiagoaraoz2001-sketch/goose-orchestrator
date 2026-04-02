"""Orchestrator — top-level glue wiring router → pool → worker dispatcher → result assembly."""

from __future__ import annotations

import logging
import time

from goose_orchestrator.config_manager import ConfigManager
from goose_orchestrator.model_pool import ModelPool
from goose_orchestrator.router import TaskPlan, TaskRouter
from goose_orchestrator.worker import StepResult, WorkerDispatcher

log = logging.getLogger(__name__)


class Orchestrator:
    """Singleton orchestration engine. Owns the model pool and dispatcher."""

    _instance: Orchestrator | None = None

    def __new__(cls) -> Orchestrator:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._pool = ModelPool()
        self._router: TaskRouter | None = None
        self._dispatcher: WorkerDispatcher | None = None

    async def _ensure_ready(self) -> None:
        """Boot: load orchestrator model, create router & dispatcher."""
        if self._router is not None:
            return

        cfg = ConfigManager()
        provider = await self._pool.ensure_orchestrator_loaded()
        self._router = TaskRouter(provider, cfg.cfg.orchestrator.model)
        self._dispatcher = WorkerDispatcher(self._pool)
        log.info("Orchestrator ready (model=%s)", cfg.cfg.orchestrator.model)

    async def run(self, prompt: str) -> str:
        """Main entry: route, dispatch, assemble."""
        await self._ensure_ready()
        assert self._router is not None and self._dispatcher is not None

        t0 = time.monotonic()

        # Phase 1: Plan
        plan: TaskPlan = await self._router.plan(prompt)
        plan_time = time.monotonic() - t0
        log.info("Plan created in %.1fs: %d steps — %s", plan_time, len(plan.steps), plan.summary)

        # Phase 2: Execute
        results: list[StepResult] = await self._dispatcher.execute_plan(plan.steps)
        total_time = time.monotonic() - t0

        # Phase 3: Assemble
        return self._assemble(plan, results, total_time)

    async def run_with_events(self, prompt: str):
        """Generator-style entry that yields events for WebSocket streaming."""
        await self._ensure_ready()
        assert self._router is not None and self._dispatcher is not None

        t0 = time.monotonic()

        yield {"type": "status", "message": "Planning..."}

        plan: TaskPlan = await self._router.plan(prompt)
        plan_time = time.monotonic() - t0

        yield {
            "type": "plan",
            "summary": plan.summary,
            "steps": [
                {"id": s.id, "role": s.role, "sub_prompt": s.sub_prompt[:200],
                 "depends_on": s.depends_on}
                for s in plan.steps
            ],
            "plan_time_s": round(plan_time, 1),
        }

        results: list[StepResult] = await self._dispatcher.execute_plan(plan.steps)
        total_time = time.monotonic() - t0

        for r in results:
            yield {
                "type": "step_result",
                "step_id": r.step_id,
                "role": r.role,
                "model": r.model,
                "success": r.success,
                "text": r.text if r.success else "",
                "error": r.error,
                "elapsed_s": round(r.elapsed_s, 1),
            }

        succeeded = sum(1 for r in results if r.success)
        yield {
            "type": "complete",
            "total_time_s": round(total_time, 1),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
            "full_output": self._assemble(plan, results, total_time),
        }

    def _assemble(self, plan: TaskPlan, results: list[StepResult], total_time: float) -> str:
        """Combine worker results into a coherent response."""
        parts: list[str] = []

        succeeded = sum(1 for r in results if r.success)
        total_in = sum(r.input_tokens for r in results)
        total_out = sum(r.output_tokens for r in results)

        parts.append(
            f"**Orchestrator Plan**: {plan.summary}\n"
            f"**Execution**: {succeeded}/{len(results)} steps succeeded "
            f"in {total_time:.1f}s | {total_in} in / {total_out} out tokens\n"
        )

        for result in results:
            if result.success:
                parts.append(
                    f"---\n"
                    f"### Step {result.step_id}: {result.role} "
                    f"({result.model}, {result.elapsed_s:.1f}s)\n\n"
                    f"{result.text}"
                )
            else:
                parts.append(
                    f"---\n"
                    f"### Step {result.step_id}: {result.role} — FAILED\n"
                    f"Error: {result.error}"
                )

        return "\n\n".join(parts)

    def pool_status(self) -> dict:
        return self._pool.status()

    async def reset(self) -> str:
        """Unload all workers and reset state."""
        await self._pool.unload_all_workers()
        return "All worker models unloaded. Orchestrator model retained."
