"""CrewAI integration — translates task plans into CrewAI Crews for execution."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

from goose_orchestrator.config_manager import ConfigManager
from goose_orchestrator.model_pool import ModelPool
from goose_orchestrator.router import TaskStep

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


def _build_llm_string(provider: str, model: str, cfg: ConfigManager) -> str:
    """Build a CrewAI-compatible LLM string for the given provider/model.

    CrewAI uses litellm under the hood, so we use litellm's provider prefixes.
    """
    ep = cfg.provider_endpoint(provider)

    if provider == "ollama":
        endpoint = ep.endpoint if ep else "http://localhost:11434"
        os.environ.setdefault("OLLAMA_API_BASE", endpoint)
        return f"ollama/{model}"
    elif provider == "anthropic":
        if ep and ep.api_key_env:
            key = os.environ.get(ep.api_key_env, "")
            if key:
                os.environ.setdefault("ANTHROPIC_API_KEY", key)
        return f"anthropic/{model}"
    elif provider == "openai":
        if ep and ep.api_key_env:
            key = os.environ.get(ep.api_key_env, "")
            if key:
                os.environ.setdefault("OPENAI_API_KEY", key)
        if ep and ep.endpoint and "openai.com" not in ep.endpoint:
            os.environ["OPENAI_API_BASE"] = ep.endpoint
            return f"openai/{model}"
        return model  # native OpenAI models don't need prefix
    else:
        return f"openai/{model}"


class CrewManager:
    """Manages CrewAI-based worker execution with VRAM-aware model lifecycle."""

    def __init__(self, pool: ModelPool) -> None:
        self._pool = pool
        cfg = ConfigManager()
        self._max_workers = cfg.cfg.resources.max_simultaneous_workers
        self._timeout = cfg.cfg.resources.worker_generation_timeout_s

    async def execute_plan(
        self,
        steps: list[TaskStep],
        step_outputs: dict[int, str] | None = None,
        on_step_start: object = None,
        on_step_end: object = None,
    ) -> list[StepResult]:
        """Execute task steps using CrewAI agents, respecting dependencies."""
        if step_outputs is None:
            step_outputs = {}

        results: dict[int, StepResult] = {}
        completed: dict[int, asyncio.Event] = {s.id: asyncio.Event() for s in steps}
        step_map = {s.id: s for s in steps}
        semaphore = asyncio.Semaphore(self._max_workers)

        async def _run_step(step: TaskStep) -> None:
            # Wait for dependencies
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

            # Preload hint
            if step.preload_hint:
                asyncio.create_task(self._pool.preload_hint(step.preload_hint))

            async with semaphore:
                result = await self._execute_with_crewai(step, full_prompt)

            results[step.id] = result
            if result.success:
                step_outputs[step.id] = result.text
            completed[step.id].set()

        tasks = [asyncio.create_task(_run_step(s)) for s in steps]
        await asyncio.gather(*tasks, return_exceptions=True)

        return [results[s.id] for s in steps if s.id in results]

    async def _execute_with_crewai(self, step: TaskStep, prompt: str) -> StepResult:
        """Execute a single step using a CrewAI Agent + Task."""
        t0 = time.monotonic()
        cfg = ConfigManager()
        worker_cfg = cfg.get_worker(step.role)

        if worker_cfg is None:
            return StepResult(
                step_id=step.id, role=step.role, model="unknown",
                text="", input_tokens=0, output_tokens=0,
                elapsed_s=0, success=False, error=f"Unknown role: {step.role}",
            )

        try:
            # Ensure model is loaded in VRAM (for local providers)
            provider_inst, model_name = await self._pool.acquire_worker(step.role)

            # Build LLM string for CrewAI
            llm_string = _build_llm_string(worker_cfg.provider, worker_cfg.model, cfg)

            # Run CrewAI in a thread to avoid blocking the event loop
            result_text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self._run_crew_sync, step, prompt, llm_string, worker_cfg.temperature
                ),
                timeout=self._timeout,
            )

            elapsed = time.monotonic() - t0
            await self._pool.release_worker(model_name)

            log.info("Step %d [%s] completed via CrewAI in %.1fs", step.id, step.role, elapsed)

            return StepResult(
                step_id=step.id, role=step.role, model=worker_cfg.model,
                text=result_text, input_tokens=0, output_tokens=0,
                elapsed_s=elapsed, success=True,
            )

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            return StepResult(
                step_id=step.id, role=step.role, model=worker_cfg.model,
                text="", input_tokens=0, output_tokens=0,
                elapsed_s=elapsed, success=False,
                error=f"Timed out after {self._timeout}s",
            )
        except Exception as e:
            elapsed = time.monotonic() - t0
            log.error("Step %d [%s] CrewAI error: %s", step.id, step.role, e)
            return StepResult(
                step_id=step.id, role=step.role, model=worker_cfg.model,
                text="", input_tokens=0, output_tokens=0,
                elapsed_s=elapsed, success=False, error=str(e),
            )

    def _run_crew_sync(
        self, step: TaskStep, prompt: str, llm_string: str, temperature: float
    ) -> str:
        """Synchronous CrewAI execution (runs in thread pool)."""
        from crewai import Agent, Crew, Process, Task

        agent = Agent(
            role=step.role.replace("_", " ").title(),
            goal=f"Complete the assigned {step.role} task with high quality",
            backstory=(
                f"You are a specialized {step.role.replace('_', ' ')} assistant. "
                f"You excel at tasks in your domain and produce thorough, accurate results."
            ),
            llm=llm_string,
            verbose=False,
            allow_delegation=False,
            max_iter=3,
            temperature=temperature,
        )

        task = Task(
            description=prompt,
            expected_output="A thorough, well-structured response addressing the task.",
            agent=agent,
        )

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=False,
        )

        result = crew.kickoff()
        return str(result)
