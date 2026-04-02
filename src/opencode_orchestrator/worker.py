"""Worker dispatcher — executes task steps against loaded models with concurrency control."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from opencode_orchestrator.config_manager import ConfigManager
from opencode_orchestrator.model_pool import ModelPool
from opencode_orchestrator.providers.base import GenerateRequest, GenerateResponse
from opencode_orchestrator.router import TaskStep

log = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of executing a single task step."""
    step_id: int
    role: str
    model: str
    text: str
    input_tokens: int
    output_tokens: int
    elapsed_s: float
    success: bool
    error: str | None = None


class WorkerDispatcher:
    """Semaphore-gated, dependency-aware worker execution engine."""

    def __init__(self, pool: ModelPool) -> None:
        cfg = ConfigManager()
        self._pool = pool
        self._max_workers = cfg.cfg.resources.max_simultaneous_workers
        self._semaphore = asyncio.Semaphore(self._max_workers)
        self._timeout = cfg.cfg.resources.worker_generation_timeout_s

    async def execute_plan(self, steps: list[TaskStep], step_outputs: dict[int, str] | None = None) -> list[StepResult]:
        """Execute all steps respecting dependency ordering and concurrency limits.

        Returns results in completion order.
        """
        if step_outputs is None:
            step_outputs = {}

        results: dict[int, StepResult] = {}
        completed: dict[int, asyncio.Event] = {s.id: asyncio.Event() for s in steps}
        step_map = {s.id: s for s in steps}

        async def _run_step(step: TaskStep) -> None:
            # Wait for all dependencies
            for dep_id in step.depends_on:
                if dep_id in completed:
                    await completed[dep_id].wait()

            # Build context from dependency outputs
            context_parts: list[str] = []
            for dep_id in step.depends_on:
                if dep_id in step_outputs:
                    context_parts.append(
                        f"[Output from step {dep_id} ({step_map[dep_id].role})]:\n"
                        f"{step_outputs[dep_id]}"
                    )

            full_prompt = step.sub_prompt
            if context_parts:
                full_prompt = "\n\n".join(context_parts) + "\n\n" + full_prompt

            # Fire preload hint before acquiring semaphore (non-blocking)
            if step.preload_hint:
                asyncio.create_task(self._pool.preload_hint(step.preload_hint))

            async with self._semaphore:
                result = await self._execute_single(step, full_prompt)

            results[step.id] = result
            if result.success:
                step_outputs[step.id] = result.text
            completed[step.id].set()

        # Launch all steps — they self-gate on dependencies + semaphore
        tasks = [asyncio.create_task(_run_step(s)) for s in steps]
        await asyncio.gather(*tasks, return_exceptions=True)

        return [results[s.id] for s in steps if s.id in results]

    async def _execute_single(self, step: TaskStep, prompt: str) -> StepResult:
        """Execute a single step against the appropriate worker model.

        For roles with tools (e.g. deep_research has web_search), the tools
        are executed BEFORE the LLM call and their output is prepended to the
        prompt as context. For the local_rag role, the embedding model runs
        instead of a chat model — it returns ranked chunks directly.
        """
        t0 = time.monotonic()
        cfg = ConfigManager()
        worker_cfg = cfg.get_worker(step.role)

        try:
            # -- Phase 1: Run any assigned tools to gather context --
            tool_context = await self._run_tools(step, prompt, worker_cfg)

            # Special case: local_rag with embedding model returns directly
            if step.role == "local_rag" and tool_context:
                elapsed = time.monotonic() - t0
                return StepResult(
                    step_id=step.id, role=step.role,
                    model=worker_cfg.model if worker_cfg else "unknown",
                    text=tool_context, input_tokens=0, output_tokens=0,
                    elapsed_s=elapsed, success=True,
                )

            # -- Phase 2: LLM generation with tool context --
            provider, model = await self._pool.acquire_worker(step.role)
            temperature = worker_cfg.temperature if worker_cfg else 0.7

            augmented_prompt = prompt
            if tool_context:
                augmented_prompt = (
                    f"## Context gathered by tools:\n\n{tool_context}\n\n"
                    f"---\n\n## Task:\n\n{prompt}"
                )

            req = GenerateRequest(
                model=model,
                prompt=augmented_prompt,
                system=f"You are a specialized {step.role} assistant. "
                       f"Be thorough but concise. Stay within your area of expertise.",
                max_tokens=step.context_budget,
                temperature=temperature,
            )

            log.info("Step %d [%s] generating with %s (temp=%.1f, budget=%d, tool_ctx=%d chars)",
                     step.id, step.role, model, temperature, step.context_budget,
                     len(tool_context))

            resp: GenerateResponse = await asyncio.wait_for(
                provider.generate(req),
                timeout=self._timeout,
            )

            elapsed = time.monotonic() - t0
            log.info("Step %d [%s] completed in %.1fs (%d tokens)",
                     step.id, step.role, elapsed, resp.output_tokens)

            await self._pool.release_worker(model)

            return StepResult(
                step_id=step.id,
                role=step.role,
                model=model,
                text=resp.text,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                elapsed_s=elapsed,
                success=True,
            )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            log.error("Step %d [%s] timed out after %.1fs", step.id, step.role, elapsed)
            return StepResult(
                step_id=step.id,
                role=step.role,
                model=worker_cfg.model if worker_cfg else "unknown",
                text="",
                input_tokens=0,
                output_tokens=0,
                elapsed_s=elapsed,
                success=False,
                error=f"Timed out after {self._timeout}s",
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            log.error("Step %d [%s] failed: %s", step.id, step.role, e)
            return StepResult(
                step_id=step.id,
                role=step.role,
                model=worker_cfg.model if worker_cfg else "unknown",
                text="",
                input_tokens=0,
                output_tokens=0,
                elapsed_s=elapsed,
                success=False,
                error=str(e),
            )

    async def _run_tools(self, step: TaskStep, prompt: str, worker_cfg) -> str:
        """Execute pre-generation tools for a step. Returns context string."""
        if worker_cfg is None:
            return ""

        tools = worker_cfg.tools or []
        if not tools:
            return ""

        from opencode_orchestrator.tools import searxng_search, searxng_fetch_url, embed_and_rank

        parts: list[str] = []

        for tool_name in tools:
            try:
                if tool_name == "web_search":
                    # Extract a search query from the sub-prompt
                    result = await searxng_search(prompt[:200], max_results=8)
                    parts.append(result)

                elif tool_name == "url_fetch":
                    # Only fetch if the prompt contains a URL
                    import re
                    urls = re.findall(r'https?://[^\s<>"]+', prompt)
                    for url in urls[:3]:
                        result = await searxng_fetch_url(url)
                        parts.append(result)

                elif tool_name == "semantic_search":
                    # For RAG: embed the query (the orchestrator passes chunks downstream)
                    result = f"[Embedding model ready for semantic search on: {prompt[:100]}]"
                    parts.append(result)

            except Exception as e:
                log.warning("Tool %s failed for step %d: %s", tool_name, step.id, e)

        return "\n\n".join(parts)
