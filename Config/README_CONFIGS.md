# Configuration Guide

This directory holds every YAML config the framework runs from, plus a few
templates you can copy. A run is fully described by **one YAML file** passed
to `main.py --config <path>`. That YAML picks one task list, one toolkit,
one environment adapter, one agent blueprint, and one model provider.

> See the top-level `README.md` for the four-folder layout
> (`Benchmark/`, `Toolkit/`, `Environment/`, `Agent/`) that every config
> stitches together.

---

## What's in this directory

```
Config/
├── README_CONFIGS.md                     # this file
├── config.yaml                           # working scratch config (vllm + openai-server example)
├── config_fail_analysis.yaml             # standalone config for Evaluation/fail_analysis.py
│
├── config_template_minimal.yaml          # smallest runnable config
├── config_template_full.yaml             # every field, with comments
├── config_template_local_model.yaml     # transformers / vLLM
├── config_template_multi_agent.yaml     # multi-agent (entry agent + workers)
├── config_template_evaluation.yaml      # eval_best.py + judge setup
│
├── config_AgentBench/                    # 8 yamls: dbbench, os_interaction (+ docker), webshop,
│                                         #          knowledgegraph, ltp, card_game, test_website
├── config_MultiAgentBench/               # research, coding, bargain, werewolf, db
├── config_tau/                           # τ-bench   (airline, …)
├── config_tau2/                          # τ²-bench  (airline, retail, telecom)
├── confi_eval_tau/                       # offline eval_best.py configs for τ²-bench
├── config_BFCL/                          # ~38 yamls — BFCL v4 sub-tasks
│                                         #   simple_{python,java,javascript}, multiple, parallel,
│                                         #   exec_*, live_*, irrelevance, relevance,
│                                         #   multi_turn_{base,composite,long_context,miss_func,miss_param},
│                                         #   memory_{kv,vector,rec_sum,generate_*}, web_*, sql, rest
├── config_AgentSafetyBench/
└── config_browsecomp/
```

The bundled benchmark configs reference paths like `./Benchmark/...`,
`./Toolkit/...`, `./Environment/...`. They work as-is once the HuggingFace
dataset has been extracted at the repo root (top-level README, Step 1).

> ⚠️ The folder really is named `confi_eval_tau` (typo preserved in repo).

---

## Templates

| Template                              | Use when                                                  |
|---------------------------------------|-----------------------------------------------------------|
| `config_template_minimal.yaml`        | Smallest example — `Benchmark` + `Model` + `Agent` + `Output` only |
| `config_template_full.yaml`           | Reference: every field with inline comments               |
| `config_template_local_model.yaml`    | Local Transformers or vLLM                                |
| `config_template_multi_agent.yaml`    | Multi-agent (entry agent + workers)                       |
| `config_template_evaluation.yaml`     | Offline scoring with `Evaluation/eval_best.py`            |

```bash
cp Config/config_template_minimal.yaml Config/my_run.yaml
# edit:
#   Benchmark.path        → your task file
#   Model.providers.<p>   → endpoint + key (or local model path)
#   Agent.agent_dir       → your agent blueprint .jsonl
#   Output.{log,save}_dir
python main.py --config Config/my_run.yaml
```

---

## Config Schema (what each section does, what the code actually reads)

A config has up to nine top-level keys. **Required:** `Benchmark`, `Model`,
`Agent`. Everything else has defaults or is consumed only by
`Evaluation/eval_best.py` / `fail_analysis.py`.

### `Benchmark` — what to run

```yaml
Benchmark:
  path: ./Benchmark/AgentBench/dbbench/standard_updated_instructions.jsonl
  type: single-agent multi-round
  name: card_game            # optional, only used for env-context labelling
  multi_turn: true           # optional, forces multi-turn execution path
  per_task_tools: false      # true → look up tools under Toolkit/<bench>/task_<id>/
  start_idx: 1               # 1-based inclusive; null/omitted = from start
  end_idx:   50              # 1-based inclusive; null/omitted = to end
```

`type` values that exist in the bundled configs:

| `Benchmark.type`                       | Where it's used                            |
|----------------------------------------|--------------------------------------------|
| `single-agent multi-round`             | AgentBench, BFCL, browsecomp               |
| `single-agent multi-round task`        | AgentSafetyBench (legacy "… task" suffix)  |
| `single-agent single-round`            | available, no bundled config uses it       |
| `multi-agent`                          | TauBench (config_tau)                      |
| `multi-agent multi-round`              | Tau2Bench, MultiAgentBench/coding          |
| `multi-agent task`                     | MultiAgentBench/research                   |

Internally `Utils/agent_utils.py` normalises these via `AGENT_MODE_ALIASES`,
so case / underscores / a trailing `task` are tolerated.

### `Toolkit` — function definitions

```yaml
Toolkit:
  path: ./Toolkit/AgentBench/dbbench
  generated_dir: ./Toolkit/BFCL/generated_tools   # only BFCL uses this
  loader: ./Toolkit/custom_loader.py              # optional override
  scan_dirs: [...]                                # optional extra search dirs
```

If `Benchmark.per_task_tools: true`, the runner instead looks for
`Toolkit/<bench>/task_<id>/` directories — used by BFCL and
AgentSafetyBench, where each task ships its own function set. If the
runner detects per-task tool subdirectories at `path/`, it auto-enables
`per_task_tools` even if you didn't set it (see `main.py:115`).

### `Environment` — runtime side-effects

```yaml
Environment:
  path: ./Environment/AgentBench/dbbench
  type: per-task              # per-task | global | none/null
```

Aliases handled by `Utils/environment_utils.py`:

| You write                                       | Resolved to |
|-------------------------------------------------|-------------|
| `per-task` / `per_task` / `per-benchmark` / `benchmark` | `per-task` |
| `global` / `all` / `full`                        | `global`    |
| `none` / `null` / section omitted                | `none`      |

`per-task` requires each task in the benchmark file to carry its own
environment path; `global` boots one shared environment for the whole
batch.

### `Model` — LLM provider

```yaml
Model:
  provider: openai-server     # which providers.<name> block to activate
  parameters:                 # merged into the active provider
    temperature: 0.0
    top_p: null
    max_tokens: 4096
    timeout: 60

  providers:
    openai-server:            # OpenAI-compatible endpoint (vLLM/SGLang/proxy/etc.)
      model_id: gpt-4o-mini
      api_base: http://your-api-server:port/v1
      api_key:  "your-api-key-here"
      organization: null
      project: null
      client_kwargs: {}

    vllm:                     # local vLLM, model loaded in-process
      model_id: /path/to/Qwen3-VL-2B-Instruct
      model_kwargs:
        tensor_parallel_size: 4
        gpu_memory_utilization: 0.90
        max_model_len: 4096
        dtype: auto
        rope_scaling: { rope_type: default, factor: 1.0 }

    transformers:             # local HF transformers
      model_id: /path/to/Qwen3-VL-2B-Instruct
      device_map: auto
      torch_dtype: auto
      trust_remote_code: true
      model_kwargs: { ... }

    litellm:                  # any provider via LiteLLM
      model_id: anthropic/claude-3-5-sonnet-20241022
      api_key: "..."

    inference-client:         # HuggingFace Inference API
      model_id: meta-llama/Llama-3.1-8B-Instruct
      token: "..."
```

Supported providers (see `Utils/model_utils.py`):
`openai-server` (alias: `openai`),
`vllm`,
`transformers`,
`litellm`,
`inference-client` (aliases: `inference`, `hf-inference`).

Only the block named by `Model.provider` is loaded; other blocks can stay
in the file as alternatives. `Model.parameters` is shallow-merged into the
selected provider, so global defaults can be overridden per provider.

### `Agent` — the blueprint

```yaml
Agent:
  type: single-agent multi-round    # see AGENT_MODE_ALIASES
  agent_dir: ./Agent/AgentBench/dbbench/Agent.jsonl
  agent_type: ToolCallingAgent      # ToolCallingAgent | CodeAgent
                                    # aliases: react, toolcalling, code
  stream_outputs: false
  planning_interval: -1             # -1 default; 0 disables; N plans every N steps
  max_tool_threads: 1               # parallel tool calls within one step
  fill_with_all_tools: false        # true → ignore blueprint allowed_tools, use all
  add_base_tools: false             # add smolagents base toolset
  max_steps: 110                    # hard cap on agent steps (used by card_game)
  prompt_templates: None            # path to override smolagents prompts
  entry_agent_name: Agent           # multi-agent only — must match a name in agent_dir
  max_attempts: 3                   # retry budget for tool calls (also see top-level Retry:)
```

`agent_dir` is a JSONL file (or a directory of `.jsonl`); each line is one
agent blueprint. Schema is documented in
`Agent/AGENT_DEFINITION_GUIDE.md`, `Agent/FIELD_REFERENCE.md`,
`Agent/QUICK_REFERENCE.md`.

`Agent.type` must be compatible with `Benchmark.type` (single-agent ↔
single-agent, multi-agent ↔ multi-agent).

### `Output` — where artefacts go

```yaml
Output:
  log_dir:  ./Results/logs/AgentBench/dbbench       # per-step trace JSONL
  save_dir: ./Results/outputs/AgentBench/dbbench    # final result JSONL
  eval_results: ./Results/metrics.json              # summary metrics (optional)
  include_environment: false                        # snapshot env state per task
  environment_archive_dir: ./Results/environment/AgentBench/dbbench
  realtime_save: true                               # write each task's output as it finishes
  run_timestamp: null                               # YYYYMMDD_HHMMSS to resume into a folder
  save_detailed_steps: false                        # extra per-step breakdown
```

Each run produces files of the form
`<model>_logs_<YYYYMMDD_HHMMSS>.jsonl` and
`<model>_results_<YYYYMMDD_HHMMSS>.jsonl`. `realtime_save: true` (default)
flushes per task so a crashed run keeps partial results.

### `Evaluation` — two schemas live here

The codebase carries two evaluation paths and the YAMLs reflect that.
Pick whichever your eval target uses; templates and bundled benchmark
configs lean on the **inline (legacy)** schema, while
`Evaluation/eval_best.py` reads the **`type:` schema**. Some configs (e.g.
`config_AgentBench/config_agentbench_card_game.yaml`) ship both.

**A. Inline / legacy schema** — used by AgentBench configs and the metrics
written into `Output.eval_results`:

```yaml
Evaluation:
  enabled: true
  mode: rule                    # rule | model
  metrics: [Task Score]
  judge_model:
    model_id: gpt-4o
    api_base: http://your-api-server:port/v1
    api_key:  "your-api-key-here"
  prompts: Evaluation/prompt_templates/with_label_contains.yaml
  logs:
    dir: ./Results/logs/AgentBench/dbbench
  success_threshold: 0.5
  max_retries: 3
  score_aggregation: sum         # sum | average
```

**B. `eval_best.py` schema** — used by `confi_eval_tau/`, MultiAgentBench
research, and the evaluation template:

```yaml
Evaluation:
  type: actions                  # actions | llm | both | all
  save_dir: ./Evaluation/results
  server:                        # required when type ∈ {llm, both, all}
    model_id: gpt-4o
    api_base: https://api.openai.com/v1
    api_key:  "your-api-key-here"
    judge_prompt_template: Evaluation/prompt_templates/AgentBench(LTP).yaml
    # system: "..."              # optional; overridden by template
    # evaluate: |                 # optional; overridden by template
    #   Task: {instruction}
    #   Expected: {label}
    #   Agent Result: {result}
```

| `type`            | Behaviour                                                                            |
|-------------------|--------------------------------------------------------------------------------------|
| `actions`         | Hash-compares post-run env archive against the expected `actions` field on the task |
| `llm`             | Calls the judge model with the configured prompt template against `task.label`      |
| `both` / `all`    | Runs both; final score = `action_score * llm_score` when both are present           |

Judge prompt templates live in `Evaluation/prompt_templates/`. They are
YAML with `system` and `evaluate` fields; the `evaluate` body may
reference `{instruction}`, `{label}`, `{final_memory}`, `{result}`,
`{log}`, `{environment}`.

### `Result` — log discovery for `eval_best.py`

```yaml
Result:
  log_dir:  ./Results/logs/AgentBench/dbbench
  save_dir: ./Results/outputs/AgentBench/dbbench
  environment_archive_dir: ./Results/environment/AgentBench/dbbench
  run_timestamp: 20260507_120000   # filter to one run; null = latest
  model_tag: gpt-4o-mini           # filter to one model
```

Only `Evaluation/eval_best.py` reads this section. `--timestamp` and
`--model` CLI flags override `run_timestamp` / `model_tag`.

### `Execution` — parallelism and resume

```yaml
Execution:
  max_workers: 8                   # parallel tasks (1 for local models)
  task_timeout: 300                # seconds (optional)
  continue_on_error: true          # don't abort batch on a single failure
  resume_enabled: true             # default; honour run_timestamp to resume
  resume_timestamp: 20260507_120000 # equivalent to --resume-timestamp CLI flag
```

For local Transformers/vLLM, set `max_workers: 1` — the model is the
bottleneck and parallelism only causes contention.

### `Retry` — top-level retry budget

```yaml
Retry:
  max_attempts: 3
```

Read by `main.py` and merged with `Agent.Retry` and `Agent.max_attempts`.
Used as the per-task retry count when a task throws.

---

## Mapping configs to benchmarks

### AgentBench — `config_AgentBench/`

```yaml
Benchmark.type: single-agent multi-round
Environment.type: per-task
Evaluation: { enabled: true, mode: rule | model, ... }   # inline schema
```

| File                                  | Notes                                        |
|---------------------------------------|----------------------------------------------|
| `config_agentbench_db.yaml`           | DBBench, rule-based scoring                  |
| `config_AgentBench_os_docker.yaml`    | OS interaction inside Docker                 |
| `config_os_interaction.yaml`          | OS interaction, host shell                   |
| `config_webshop.yaml`                 | Webshop (needs Webshop server running)       |
| `config_knowledgegraph.yaml`          | KG (Freebase-style)                          |
| `config_ltp.yaml`                     | Lateral Thinking Puzzle, judge-based         |
| `config_agentbench_card_game.yaml`    | Card game, ships **both** Evaluation schemas |
| `config_test_website.yaml`            | Synthetic web testing                        |

### BFCL v4 — `config_BFCL/`

```yaml
Benchmark.per_task_tools: true             # each task brings its own tool set
Toolkit.generated_dir: ./Toolkit/BFCL/generated_tools
```

`per_task_tools` is the defining trait. `multi_turn_*`, `memory_*`,
`web_*`, `sql`, `rest` use real environments; `simple_*`, `multiple`,
`parallel*`, `irrelevance`, `relevance`, `live_*` are pure
function-calling.

### MultiAgentBench — `config_MultiAgentBench/`

```yaml
Benchmark.type: multi-agent multi-round | multi-agent task
Agent.type: multi-agent
Agent.entry_agent_name: <name from your agent JSONL>     # e.g. Manager, UserAgent
Model.parameters.temperature: 0.0–0.7                    # bargain/werewolf benefit from diversity
Evaluation.type: llm                                     # collaboration is judged
```

`config_MultiAgentBench_coding.yaml` results are typically scored offline
by `Evaluation/evalulate_multiagentbench_coding.py` (unit-test style),
not by `eval_best.py`.

### τ-bench / τ²-bench

- `config_tau/` — τ-bench (`Benchmark/TauBench/...`), `Agent.type: multi-agent`
- `config_tau2/` — τ²-bench (`Benchmark/Tau2Bench/...`), `Agent.type: multi-agent`,
  entry agent typically `UserAgent`
- `confi_eval_tau/` — **offline** eval_best.py configs that re-score
  existing logs without re-running the agent. They use `Evaluation.type: actions`
  plus a `Result:` block to point at the previously-run logs.

### AgentSafetyBench — `config_AgentSafetyBench/`

```yaml
Benchmark.type: "single-agent multi-round task"   # legacy suffix
Benchmark.per_task_tools: true                    # each task has its own (sometimes risky) tools
Environment.type: per-task                        # isolate side effects
```

### BrowseComp — `config_browsecomp/`

Pure browsing benchmark; toolkit at `./Toolkit/browsecomp` (kept
deliberately empty so the agent uses only its built-in browsing tools).
`config_browsecomp_down.yaml` is the reduced-quota debugging variant.

### Local open-source models — `config_template_local_model.yaml`, `config.yaml`

```yaml
Model.provider: vllm                # or transformers
Execution.max_workers: 1            # one in-process model, one runner
```

VRAM rules of thumb (fp16):

| Model size   | VRAM     | Suggestion                          |
|--------------|----------|-------------------------------------|
| 7–8 B        | ~16 GB   | single GPU, `dtype: float16`        |
| 13 B         | ~26 GB   | single GPU, `dtype: float16`        |
| 70 B         | ~140 GB  | vLLM `tensor_parallel_size: 4`      |
| 70 B (4-bit) | ~35 GB   | transformers `load_in_4bit: true`   |

---

## Common edits

```yaml
# Switch from a hosted API to local vLLM
Model:
  provider: vllm
  providers:
    vllm:
      model_id: /path/to/Qwen3-30B-Instruct
      model_kwargs: { tensor_parallel_size: 4, gpu_memory_utilization: 0.9 }

# Smoke-test on the first 5 tasks
Benchmark: { start_idx: 1, end_idx: 5 }

# Debug-friendly run
Execution: { max_workers: 1 }
Agent:     { stream_outputs: true }

# Disable evaluation entirely (just collect raw logs)
Evaluation: { enabled: false }       # legacy schema
# or omit Evaluation: and Result: sections altogether

# Re-key outputs for a named experiment
Output:
  log_dir:  ./Results/logs/exp_qwen30b_dbbench
  save_dir: ./Results/outputs/exp_qwen30b_dbbench
```

---

## Running

```bash
# Whole batch (start_idx / end_idx slice from Benchmark)
python main.py --config Config/config_AgentBench/config_agentbench_db.yaml

# Single task by id (overrides the slice)
python main.py --config Config/<...>.yaml --task task_007

# Resume a previous run by reusing its timestamp folder
python main.py --config Config/<...>.yaml --resume-timestamp 20260507_120000

# Interactive REPL with a single agent
python main.py --config Config/<...>.yaml --interactive
```

Offline scoring with `eval_best.py` (uses `Evaluation:` schema B + `Result:`):

```bash
python Evaluation/eval_best.py --config Config/confi_eval_tau/eval_config_actions_airline.yaml
python Evaluation/eval_best.py --config Config/<...>.yaml --timestamp 20260507_120000
python Evaluation/eval_best.py --config Config/<...>.yaml --model gpt-4o-mini
```

---

## Troubleshooting

```bash
# 1. Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('Config/my_run.yaml'))"

# 2. Verify referenced paths exist
ls ./Benchmark/AgentBench/dbbench/standard_updated_instructions.jsonl
ls ./Toolkit/AgentBench/dbbench
ls ./Environment/AgentBench/dbbench
ls ./Agent/AgentBench/dbbench/Agent.jsonl
```

| Symptom                                       | Likely cause                                                                              |
|-----------------------------------------------|-------------------------------------------------------------------------------------------|
| `Model provider is not specified`             | `Model.provider` missing                                                                  |
| `Unsupported model provider 'X'`              | Not in `{openai-server, vllm, transformers, litellm, inference-client}` (or aliases)      |
| `model_id is required for provider …`         | The selected `providers.<name>` block has no `model_id`                                   |
| Agent runs but no tools fire                  | `fill_with_all_tools: false` and the blueprint's `allowed_tools` doesn't match the toolkit |
| `entry_agent_name` not found                  | Name must equal a `name` field inside the multi-agent JSONL                                |
| Per-task tools not loading                    | `Benchmark.per_task_tools: true` not set, *or* tasks lack per-task tool paths              |
| Eval JSONL is empty                           | (A) `Evaluation.enabled: false`; (B) `Evaluation.type: actions` but tasks have no `actions`; or judge `server` missing for `llm`/`both` |
| `Warning: Environment path … does not exist`  | HuggingFace dataset not extracted at repo root, or wrong `Environment.path`                |

---

## Comparing models

```bash
# 1. Duplicate a config and only change Model.providers.<name>.model_id
cp Config/config_AgentBench/config_agentbench_db.yaml /tmp/cfg_gpt4o.yaml
cp Config/config_AgentBench/config_agentbench_db.yaml /tmp/cfg_qwen.yaml
# In each: set distinct Output.log_dir / save_dir per model

# 2. Run both
python main.py --config /tmp/cfg_gpt4o.yaml
python main.py --config /tmp/cfg_qwen.yaml

# 3. Score with the same evaluator (use --model to filter to that run's logs)
python Evaluation/eval_best.py --config /tmp/cfg_gpt4o.yaml --model gpt-4o
python Evaluation/eval_best.py --config /tmp/cfg_qwen.yaml  --model Qwen3-30B-A3B-Instruct-2507
```

For a fair comparison: `temperature: 0.0`, identical
`Benchmark.start_idx`/`end_idx`, identical `Toolkit` and `Agent` blocks,
and prefer `Evaluation.type: actions` (or `mode: rule`) when ground truth
exists — judges have model bias.

---

## Failure analysis

`Evaluation/fail_analysis.py` post-processes failed runs and labels each
with one of six failure categories: parsing failure, tool invocation
error, reasoning deficit, timeout, iteration limit exceeded, context
overflow. It uses its own config — `Config/config_fail_analysis.yaml` —
not the run-time YAML. See the comments at the top of that file for
`auto`, `manual`, and `cli` modes.

```bash
python Evaluation/fail_analysis.py --config Config/config_fail_analysis.yaml
python Evaluation/fail_analysis.py --config Config/config_fail_analysis.yaml --mode cli \
       --log <path>.jsonl --eval <path>.jsonl --output <path>.jsonl
```

---

## Related reading

- `README.md` (repo root) — installation, dataset download, end-to-end run
- `Agent/AGENT_DEFINITION_GUIDE.md` — JSONL agent blueprint schema
- `Agent/FIELD_REFERENCE.md` — every blueprint field
- `Evaluation/prompt_templates/` — judge prompts shipped with the framework
- `Utils/runner.py` — how `Execution.max_workers` is dispatched
- `Utils/model_utils.py` — full provider list + alias table
- `Utils/agent_utils.py` — `AGENT_MODE_ALIASES` and `AGENT_CLASS_REGISTRY`
- `Utils/environment_utils.py` — `Environment.type` aliases
