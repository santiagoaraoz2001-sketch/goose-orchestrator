# Goose Orchestrator — Test Prompts

Copy-paste these into Goose to verify the extension is working.

## Test 1: Check extension is loaded

```
Show orchestrator status
```

**Expected**: Goose calls the `status` tool and shows all 6 worker roles with their models, VRAM budget (180 GB), and max workers (2).

## Test 2: Open the dashboard

```
Open the orchestrator dashboard
```

**Expected**: Browser opens to http://localhost:7432 with the Models page showing the orchestrator model and 6 worker roles with dropdowns.

## Test 3: Configure a worker model via chat

```
Set the code_gen worker to use devstral-small-2:Q8_0
```

**Expected**: Goose calls `configure_worker(role="code_gen", model="devstral-small-2:Q8_0")` and confirms the change.

## Test 4: Multi-step orchestration (research + summarize)

```
Research the latest developments in mixture-of-experts architectures for LLMs, then summarize the key findings in a concise report.
```

**Expected**: Goose calls `orchestrate` → the orchestrator model creates a 2-step plan (deep_research → summarizer) → deep_research worker searches SearXNG for results and generates a response → summarizer condenses it.

## Test 5: Code + math orchestration

```
Write a Python function to compute the PageRank algorithm, then prove that it converges for any stochastic matrix.
```

**Expected**: 2-step plan (code_gen → math_reasoning). Code worker generates the function, math worker provides the convergence proof.

## Test 6: Full config dump

```
Show the full orchestrator YAML config
```

**Expected**: Goose calls `list_config` and shows the complete YAML with all roles, models, temperatures, SearXNG endpoint, and embedding config.
