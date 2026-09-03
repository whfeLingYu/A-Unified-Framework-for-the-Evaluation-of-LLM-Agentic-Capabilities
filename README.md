# Agent Sandbox and Evaluation

A unified sandbox and evaluation framework for running LLM agents across a wide
range of public benchmarks. The framework decouples four concerns — **task
instructions**, **execution environment**, **tool / toolkit definitions**, and
**agent blueprints** — so the same agent can be plugged into a different
benchmark (or a new one) with only a YAML config change.

Out of the box it supports:

- **AgentBench** — DBBench, OS Interaction, Webshop, Knowledge Graph, LTP,
  Card Game, Test Website
- **MultiAgentBench** — Research, Coding, Bargain, Werewolf, DB
- **τ-bench (TauBench)** and **τ²-bench (Tau2Bench)** — airline, retail, telecom
- **BFCL v4** — function-calling, multi-turn, memory, web, etc.
- **AgentSafetyBench**
- **BrowseComp**

---

## Repository Layout

```
Agent-Sandbox-and-Evaluation/
├── main.py                     # Entry point: load config → build agent → run tasks
├── Config/                     # YAML configs, one per benchmark / sub-task
│   ├── config_AgentBench/
│   ├── config_MultiAgentBench/
│   ├── config_tau/   config_tau2/   confi_eval_tau/
│   ├── config_BFCL/
│   ├── config_AgentSafetyBench/
│   ├── config_browsecomp/
│   ├── config_template_*.yaml  # Minimal / full / multi-agent / local-model templates
│   └── README_CONFIGS.md
├── Benchmark/                  # Task instruction sets (downloaded from HuggingFace)
│   └── <BenchmarkName>/<sub-task>/...   # jsonl / json / yaml
├── Toolkit/                    # Tool / function definitions per sub-task (HF)
│   └── <BenchmarkName>/<sub-task>/...
├── Environment/                # Per-benchmark environment adapters (HF):
│   │                           #   DBs, browsers, docker shells, simulators, …
│   ├── AgentBench/  MultiAgentBench/  TauBench/  Tau2Bench/
│   ├── BFCL/        AgentSafetyBench/ browsecomp/
├── Agent/                      # Agent blueprints (jsonl) + authoring guides
│   ├── AgentBench/  MultiAgentBench/  Tau2Bench/  ...
│   ├── examples/
│   ├── AGENT_DEFINITION_GUIDE.md
│   ├── BLUEPRINT_LOADING_GUIDE.md
│   ├── FIELD_REFERENCE.md
│   └── QUICK_REFERENCE.md
├── Evaluation/                 # Scoring & failure analysis
│   ├── eval_best.py            # Main evaluator (rule + model-as-judge)
│   ├── evalulate_multiagentbench_coding.py
│   ├── fail_analysis.py / fail.py
│   └── prompt_templates/       # Judge prompts per benchmark / metric
├── Utils/                      # Runner, model loaders, tool/env utilities
│   ├── runner.py               # Sequential / parallel batch runner
│   ├── agent_utils.py
│   ├── tool_utils.py
│   ├── environment_utils.py
│   ├── result_utils.py
│   ├── model_utils.py
│   ├── benchmark_utils.py
│   └── docker/                 # Docker helpers for OS-style benchmarks
├── Results/                    # Run artefacts: logs, outputs, metrics, archives
├── smolagents/                 # Bundled `smolagents` runtime (CodeAgent, ToolCallingAgent, …)
├── requirements.txt
└── run_multiagentbench_research.sh   # Example loop runner
```

The framework keeps **four parallel directories** at the repo root that all
use the same benchmark / sub-task naming convention:

| Directory                   | Role                                            |
|-----------------------------|-------------------------------------------------|
| `Benchmark/<bench>/<task>/` | Task instructions (input)                       |
| `Toolkit/<bench>/<task>/`   | Tool / function definitions                     |
| `Environment/<bench>/<task>/` | Code that materialises the runtime env        |
| `Agent/<bench>/<task>/`     | Agent blueprint(s) (`*.jsonl`)                  |

`Benchmark/`, `Toolkit/`, and `Environment/` are all shipped as a single
HuggingFace dataset (see below); `Agent/` and `Config/` ship with this repo.
A YAML config in `Config/` is the glue that picks one item from each column.

---

## Installation

```bash
git clone <this-repo>
cd Agent-Sandbox-and-Evaluation

# Python 3.10+ recommended
python -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

Some benchmarks need extra system services:

- **AgentBench / DBBench** — local MySQL or SQLite reachable from the runner
- **AgentBench / OS Interaction** — Docker (see `Utils/docker/docker_os_quickstart.sh`)
- **AgentBench / Webshop** — the Webshop server
- **τ-bench / τ²-bench** — no external service, but model API access
- **BFCL `web_*`** — a search/crawl backend or the bundled mock

---

## Step 1 — Download Datasets from HuggingFace

The task instruction sets (`Benchmark/`), tool / function definitions
(`Toolkit/`), and per-benchmark environment assets (`Environment/`) are
distributed as a single HuggingFace dataset. Extract it **directly into the
repo root** so the three folders sit alongside `Config/`, `Agent/`, `Utils/`,
and `main.py`. You need to download according to the Hugging Face repository address provided in the paper.

### Option A — `huggingface-cli` (recommended)

```bash
pip install -U "huggingface_hub[cli]"

# Optional: log in if the dataset is gated
huggingface-cli login

# From the repo root — extracts Benchmark/, Toolkit/, Environment/ in place
huggingface-cli download <hf-org>/<hf-dataset-name> \
    --repo-type dataset \
    --local-dir . \
    --local-dir-use-symlinks False
```

### Option B — Python API

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="<hf-org>/<hf-dataset-name>",
    repo_type="dataset",
    local_dir=".",                  # repo root
    local_dir_use_symlinks=False,
)
```

### Option C — `git lfs` into a temp dir, then move

```bash
git lfs install
git clone https://huggingface.co/datasets/<hf-org>/<hf-dataset-name> _hf_tmp
mv _hf_tmp/Benchmark _hf_tmp/Toolkit _hf_tmp/Environment .
rm -rf _hf_tmp
```

After downloading, the repo root should look like:

```
Agent-Sandbox-and-Evaluation/
├── Benchmark/AgentBench/dbbench/standard_updated_instructions.jsonl
├── Benchmark/MultiAgentBench/research/...
├── Toolkit/AgentBench/dbbench/load_tools.py
├── Toolkit/MultiAgentBench/research/...
├── Environment/AgentBench/dbbench/...
├── Config/        Agent/        Utils/        Evaluation/
└── main.py
```

The bundled YAML configs reference `./Benchmark/...`, `./Toolkit/...`, and
`./Environment/...` directly — no symlinks or path edits required once the
download is in place.

> Some environments may pull additional resources on first run (e.g. docker
> images, browser binaries, model weights). The `Agent/` and `Config/`
> folders ship with this repo, so they are **not** part of the HuggingFace
> download.

---

## Step 2 — Configure a Run

Every run is driven by a single YAML file. Start from a template:

| Template                                | Use when                                  |
|-----------------------------------------|-------------------------------------------|
| `Config/config_template_minimal.yaml`   | Smallest working example                  |
| `Config/config_template_full.yaml`      | All available fields with comments        |
| `Config/config_template_evaluation.yaml`| Evaluation-only / judge configuration     |
| `Config/config_template_multi_agent.yaml`| Multi-agent (manager + workers)          |
| `Config/config_template_local_model.yaml`| Local HF / vLLM models                   |

A minimal config has five sections:

```yaml
Benchmark:
  path: ./Benchmark/AgentBench/dbbench/standard_updated_instructions.jsonl
  type: single-agent multi-round        # or single-agent single-round / multi-agent
  start_idx: 1
  end_idx: 50

Toolkit:
  path: ./Toolkit/AgentBench/dbbench

Environment:
  path: ./Environment/AgentBench/dbbench
  type: per-task                        # or shared

Model:
  provider: openai-server               # openai-server | anthropic | huggingface | vllm
  parameters:
    temperature: 0.0
    max_tokens: 4096
  providers:
    openai-server:
      model_id: gpt-4o-mini
      api_base: http://your-api-server:port/v1
      api_key: "your-api-key-here"

Agent:
  type: single-agent
  agent_dir: ./Agent/AgentBench/dbbench/Agent.jsonl
  agent_type: ToolCallingAgent          # or CodeAgent

Output:
  log_dir:  ./Results/logs/AgentBench/dbbench
  save_dir: ./Results/outputs/AgentBench/dbbench
  eval_results: ./Results/metrics.json

Evaluation:
  enabled: true
  mode: rule                            # rule | model | both
  metrics: [Task Score]
  judge_model:
    model_id: gpt-4o
    api_base: http://your-api-server:port/v1
    api_key: "your-api-key-here"

Execution:
  max_workers: 8                        # parallel tasks
```

See `Config/README_CONFIGS.md` and `Config/config_template_full.yaml` for the
full field reference (memory, planning, retries, environment archiving,
multi-agent hierarchies, …).

---

## Step 3 — Run

```bash
# Run a whole benchmark slice as defined by start_idx / end_idx
python main.py --config Config/config_AgentBench/config_agentbench_db.yaml

# Run a single task by id (overrides the slice)
python main.py --config Config/config_AgentBench/config_agentbench_db.yaml \
               --task task_007

# Resume a previous run (re-uses the existing timestamped log/output folder)
python main.py --config <config>.yaml --resume-timestamp 20260101_120000

# Interactive REPL with a single agent (good for debugging tools/prompts)
python main.py --config <config>.yaml --interactive
```

Loop-style runs (one task per process, e.g. for MultiAgentBench/research):

```bash
bash run_multiagentbench_research.sh
```

Per-run artefacts are written under `Results/`:

```
Results/
├── logs/<bench>/<task>/<model>_logs_<timestamp>.jsonl
├── outputs/<bench>/<task>/<model>_results_<timestamp>.jsonl
└── eval_results/...                # populated by Evaluation/
```

---

## Step 4 — Evaluate

Evaluation has two stages and they are independent:

1. **`eval_best.py`** — score every task. Produces a per-task JSONL with a
   numeric `score`, plus token / step / hash diagnostics.
2. **`fail_analysis.py`** — read the eval JSONL, pick the failed tasks
   (`score < threshold`), and ask an LLM to categorise *why* each one
   failed (parsing / tool / reasoning / timeout / iteration limit /
   context overflow).

Evaluation can also run **inline** during a run (set
`Evaluation.enabled: true` in the config), but that path uses the legacy
`Evaluation: { mode: rule | model, … }` schema. The recommended workflow
is **offline** with `eval_best.py`.

### 4.1 — `eval_best.py` (scoring)

`Evaluation/eval_best.py` re-reads the same YAML you ran with, locates the
log JSONL written under `Results/`, and emits a scored eval JSONL.

**CLI:**

```bash
python Evaluation/eval_best.py --config <config>.yaml \
       [--logs <path>]            # explicit log file (overrides Result.log_dir)
       [--output <path>]          # explicit output file
       [--timestamp YYYYMMDD_HHMMSS]   # filter to one run
       [--model <model_id>]            # filter to one model's logs
       [--prompt-environment <path>]   # extra source for {environment} placeholder (repeatable)
```

**Config sections it reads:**

```yaml
# What to score against
Benchmark:    { path: ... }                       # task definitions (for actions / labels)
Toolkit:      { path: ... }                       # needed to replay env actions
Environment:  { path: ..., type: per-task }       # only for `actions` / `both`

Evaluation:
  type: actions | llm | both | all
  save_dir: ./Evaluation/results                  # eval_results_<model>_<timestamp>.jsonl lands here
  server:                                          # required for llm / both / all
    model_id: gpt-4o
    api_base: https://api.openai.com/v1
    api_key:  "your-api-key-here"
    judge_prompt_template: Evaluation/prompt_templates/<bench>.yaml
    # retry: { max_attempts: 5, backoff: 1.5 }    # optional

# Where eval_best.py looks for logs
Result:
  log_dir:  ./Results/logs/<bench>/<task>
  save_dir: ./Results/outputs/<bench>/<task>      # fallback if log_dir empty
  environment_archive_dir: ./Results/environment/<bench>/<task>   # required for `actions`
  run_timestamp: 20260507_120000                   # optional filter
  model_tag: gpt-4o-mini                           # optional filter
```

**The four `Evaluation.type` values:**

| `type`    | What it does                                                                                                   | Needs                                                          |
|-----------|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| `actions` | Re-runs the gold action list in a sandbox and SHA-256 hashes every produced file; whitespace-normalised match | `Output.include_environment: true` and `environment_archive_dir` set on the original run, plus `task.actions` in benchmark |
| `llm`     | Calls the judge with `judge_prompt_template`, returns `{score, reasoning}` JSON                                 | `Evaluation.server.*`, plus `task.label` in benchmark           |
| `both` / `all` | Runs both when both are available; final = `action_score × llm_score`                                     | All of the above                                                |

Judge templates accept the placeholders `{instruction}`, `{label}`,
`{final_memory}`, `{result}`, `{log}`, `{environment}`; templates live
under `Evaluation/prompt_templates/` (one per benchmark / metric, e.g.
`AgentBench(LTP).yaml`, `with_label_contains.yaml`, BFCL AST checks).

**Examples:**

```bash
# Score one τ²-bench run (telecom) using actions only
python Evaluation/eval_best.py \
       --config Config/confi_eval_tau/eval_config_actions_telecom.yaml

# Re-score a specific run by timestamp, with judge model
python Evaluation/eval_best.py \
       --config Config/config_AgentBench/config_agentbench_card_game.yaml \
       --timestamp 20260507_120000 \
       --model gemini-3-flash-preview

# One-off: point at an explicit log file, write to an explicit output
python Evaluation/eval_best.py --config <config>.yaml \
       --logs Results/logs/<bench>/<task>/gpt-4o-mini_logs_20260507_120000.jsonl \
       --output /tmp/eval_out.jsonl
```

**Output (`eval_results_<model>_<timestamp>.jsonl`):** one line per task
with `task_id`, `score`, `hash_match`, `gold_file_hashes`,
`actual_file_hashes`, `file_details`, `total_step_count`,
`per_agent_step_counts`, `total_input_tokens`, `total_output_tokens`,
`elapsed_seconds`, and (for `llm`/`both`) `llm_score`, `llm_reasoning`.

### 4.2 — `fail_analysis.py` (failure categorisation)

`Evaluation/fail_analysis.py` consumes the **log JSONL** and the
**eval JSONL** produced above and asks an LLM to bucket each failed task
into one of six categories:

| # | Category                  | What it means                                                              |
|---|---------------------------|----------------------------------------------------------------------------|
| 1 | Parsing Failure           | Output couldn't be parsed (invalid JSON, missing fields, format violation) |
| 2 | Tool Invocation Error     | Wrong tool name, wrong parameter names, schema-violating arguments          |
| 3 | Reasoning Deficit         | Format was fine, logic was wrong (loops, wrong path, false-positive answer)|
| 4 | Timeout                   | Wall-clock or per-task time limit hit                                       |
| 5 | Iteration Limit Exceeded  | Hit `max_steps` / "Max turns reached" without a final answer                |
| 6 | Context Overflow          | Token-limit / "context length exceeded" / token-rate-limit error            |

Driven by its own config — `Config/config_fail_analysis.yaml` — *not* the
run-time YAML.

**CLI:**

```bash
python Evaluation/fail_analysis.py [--config <path>] \
       [--mode auto | manual | cli]            # override run.mode
       # cli-mode only:
       [--log <log.jsonl>] [--eval <eval.jsonl>] [--output <out.jsonl>]
       [--api_base <url>] [--model <model_id>]
```

**Three run modes:**

| mode     | When to use                                                                          | Required config keys                                       |
|----------|--------------------------------------------------------------------------------------|------------------------------------------------------------|
| `auto`   | Sweep a whole benchmark dir: matches `*_logs_<ts>.jsonl` ↔ `eval_results_*<ts>.jsonl` by **model name + timestamp**, writes one fail-analysis file per pair | `auto.{log_dir, eval_dir, output_dir}`                     |
| `manual` | Explicit, parallel triples (logs[i], evals[i], outputs[i])                            | `manual.{logs, evals, outputs}` (same length)              |
| `cli`    | One-off: pass a single triple on the command line                                     | none — `--log`, `--eval`, `--output` (and optionally `--api_base`, `--model`) |

**Failure threshold** — `threshold.fail_threshold` is the score below
which a task is considered failed (default `1.0`, i.e. anything not
perfect). Optional `use_task_id_threshold: true` lets you split by
`task_id`: tasks with `task_id > task_id_boundary` use `high_threshold`
instead. Useful when later tasks have a different scoring scale.

**Examples:**

```bash
# Sweep a whole benchmark dir (model+timestamp matching, resume-safe)
python Evaluation/fail_analysis.py --config Config/config_fail_analysis.yaml

# Override the mode in the config without editing it
python Evaluation/fail_analysis.py --config Config/config_fail_analysis.yaml --mode auto

# One-off CLI: a single (log, eval, output) triple
python Evaluation/fail_analysis.py --mode cli \
       --log    Results/logs/MAB/dbbench/gpt-4o-mini_logs_20260507_120000.jsonl \
       --eval   Evaluation/results/eval_results_gpt-4o-mini_20260507_120000.jsonl \
       --output Results/fail/MAB/dbbench/fail_analysis_gpt-4o-mini_20260507_120000.jsonl \
       --api_base http://your-api-server:port/v1 \
       --model    Qwen3-30B-A3B-Instruct-2507
```

**Output (`fail_analysis_<original_log_name>.jsonl`):** the **first line**
is an aggregate stats row, then one line per analysed failed task.

```json
{"total_failed_in_eval": 18, "total_analyzed": 18, "newly_analyzed": 18,
 "category_stats": {"Reasoning Deficit": 11, "Tool Invocation Error": 5, "Timeout": 2}}
{"index": 3, "task_id": "task_004", "score": 0.0, "failure_threshold": 1.0,
 "category": [3], "reason": "Agent looped on identical SQL queries...",
 "llm_output": "...", "log_file": "...", "eval_file": "..."}
...
```

The per-task entries are categorised by an LLM call (configured under
`api.{api_base, model_name, max_retries, timeout}` in the
`config_fail_analysis.yaml`); reruns are **resume-safe** — already-done
indices are detected by `index` in the existing output file and skipped.

### 4.3 — End-to-end recipe

```bash
# 1. Run the agent (writes logs + outputs + env archive under Results/)
python main.py --config Config/config_AgentBench/config_agentbench_db.yaml

# 2. Score with eval_best.py (writes eval_results_<model>_<ts>.jsonl)
python Evaluation/eval_best.py \
       --config Config/config_AgentBench/config_agentbench_db.yaml

# 3. Categorise failures (writes fail_analysis_*.jsonl)
#    First, set log_dir / eval_dir / output_dir + api in
#    Config/config_fail_analysis.yaml, then:
python Evaluation/fail_analysis.py --config Config/config_fail_analysis.yaml
```

### 4.4 — Benchmark-specific evaluator

MultiAgentBench/coding has its own unit-test-style evaluator (the agent
produces code, the evaluator runs the test suite):

```bash
python Evaluation/evalulate_multiagentbench_coding.py \
       --benchmark Benchmark/MultiAgentBench/coding/coding_merged_clean.jsonl \
       --results-dir Results/outputs/MultiAgentBench/coding \
       --model gpt-4o-mini
```

---

## How It Fits Together

```
                    ┌──────────────────────────────────────────┐
                    │                main.py                   │
                    └──────────────┬───────────────────────────┘
                                   │ read_config()
                                   ▼
       ┌─────────────────┬─────────────────┬─────────────────┐
       │   Benchmark     │     Toolkit     │   Environment   │
       │ (instructions)  │ (tool defs)     │ (runtime adapter)│
       └────────┬────────┴────────┬────────┴────────┬────────┘
                │                 │                 │
                ▼                 ▼                 ▼
            tasks[]         grouped_tools     env_resources
                \________________│________________/
                                 ▼
                           Agent blueprint  ──▶  smolagents runtime
                                 │            (ToolCallingAgent / CodeAgent)
                                 ▼
                           Utils/runner.py ──▶  parallel/serial execution
                                 │
                                 ▼
                              Results/   ──▶   Evaluation/
```

- **Benchmark** picks the task list (`Benchmark/...`).
- **Toolkit** picks which tools are loaded per task (`Toolkit/...`).
- **Environment** is the side-effectful runtime: a DB connection, a docker
  container, a browser, a simulated airline back-office, …
- **Agent** is a blueprint (jsonl) describing the prompt, allowed tools,
  planning interval, retry policy, etc. See `Agent/AGENT_DEFINITION_GUIDE.md`.

---

## Adding a New Benchmark

1. Drop task instructions under `Benchmark/<MyBench>/<task>/`.
2. Drop tool definitions / loaders under `Toolkit/<MyBench>/<task>/`.
3. Implement an environment adapter under `Environment/<MyBench>/<task>/`
   (it must expose the lifecycle hooks expected by
   `Utils/environment_utils.py`).
4. Author one or more agent blueprints under `Agent/<MyBench>/<task>/*.jsonl`
   (see `Agent/AGENT_DEFINITION_GUIDE.md` and `Agent/QUICK_REFERENCE.md`).
5. Add a config under `Config/config_<MyBench>/<task>.yaml`, copying from
   `Config/config_template_full.yaml`.
6. Optionally add a judge prompt under `Evaluation/prompt_templates/<MyBench>/`.

Run with `python main.py --config Config/config_<MyBench>/<task>.yaml`.

---

## Notes

- All API keys and endpoints in the bundled configs are placeholders
  (`your-api-key-here`, `http://your-api-server:port/v1`). Replace them with
  your own before running.
- `smolagents/` is a vendored copy of the smolagents runtime — the framework
  imports from it directly so you don't need to install it separately.
- `Benchmark/`, `Toolkit/`, and `Environment/` are not committed to this
  repo — fetch them from HuggingFace (see Step 1). `Results/` is produced
  per-run and is also not part of source control.


## Citation
If you find this useful, please cite our article.
```
@misc{zhu2026uniaceunifiedframeworkevaluating,
      title={UniACE: A Unified Framework for Evaluating LLM Agentic Capabilities}, 
      author={Pengyu Zhu and Lijun Li and Yaxing Lyu and Qianxin Luo and Jingyi Yang and Yi Liu and Tingfeng Hui and Xinyu Yuan and Li Sun and Sen Su and Jing Shao},
      year={2026},
      eprint={2605.27898},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2605.27898}, 
}
```
