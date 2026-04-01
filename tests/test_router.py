"""Tests for TaskRouter JSON extraction and plan parsing."""

import tempfile

import yaml

from goose_orchestrator.router import TaskPlan, TaskStep, _extract_json


def test_extract_json_direct():
    raw = '{"summary": "test", "steps": []}'
    data = _extract_json(raw)
    assert data["summary"] == "test"


def test_extract_json_from_markdown_fence():
    raw = """Here is the plan:
```json
{"summary": "fenced", "steps": [{"id": 1, "role": "code_gen", "sub_prompt": "hi"}]}
```
"""
    data = _extract_json(raw)
    assert data["summary"] == "fenced"
    assert len(data["steps"]) == 1


def test_extract_json_with_preamble():
    raw = """I'll decompose this into steps.
{"summary": "embedded", "steps": []}
And that's the plan."""
    data = _extract_json(raw)
    assert data["summary"] == "embedded"


def test_extract_json_invalid_raises():
    import pytest
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


def test_task_step_preload_hint():
    step = TaskStep(id=1, role="deep_research", sub_prompt="test", preload_hint="code_gen")
    assert step.preload_hint == "code_gen"


def test_task_plan_structure():
    plan = TaskPlan(
        steps=[
            TaskStep(id=1, role="deep_research", sub_prompt="research X"),
            TaskStep(id=2, role="code_gen", sub_prompt="implement X", depends_on=[1]),
        ],
        summary="Research then code",
    )
    assert len(plan.steps) == 2
    assert plan.steps[1].depends_on == [1]
