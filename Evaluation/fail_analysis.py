import argparse
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests
import yaml


# ==========================================
#                Config Object
# ==========================================

DEFAULT_CONFIG_PATH = "Config/config_fail_analysis.yaml"

DEFAULT_CATEGORY_MAP = {
    "1": "Parsing Failure",
    "2": "Tool Invocation Error",
    "3": "Reasoning Deficit",
    "4": "Timeout",
    "5": "Iteration Limit Exceeded",
    "6": "Context Overflow",
}


@dataclass
class FailAnalysisConfig:
    # Run mode: "auto" | "manual" | "cli"
    mode: str = "auto"

    # auto mode
    log_dir: Optional[str] = None
    eval_dir: Optional[str] = None
    output_dir: Optional[str] = None

    # manual mode
    logs: List[str] = field(default_factory=list)
    evals: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)

    # LLM API
    api_base: str = ""
    model_name: str = ""
    api_max_retries: int = 5
    api_timeout: int = 120

    # Failure threshold
    fail_threshold: float = 1.0
    use_task_id_threshold: bool = False
    task_id_boundary: int = 50
    high_threshold: float = 2.0

    # Category mapping
    category_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CATEGORY_MAP))

    @classmethod
    def from_yaml(cls, path: str) -> "FailAnalysisConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        cfg = cls()
        run = raw.get("run", {}) or {}
        cfg.mode = str(run.get("mode", cfg.mode)).lower().strip()

        auto = raw.get("auto", {}) or {}
        cfg.log_dir = auto.get("log_dir", cfg.log_dir)
        cfg.eval_dir = auto.get("eval_dir", cfg.eval_dir)
        cfg.output_dir = auto.get("output_dir", cfg.output_dir)

        manual = raw.get("manual", {}) or {}
        cfg.logs = list(manual.get("logs", []) or [])
        cfg.evals = list(manual.get("evals", []) or [])
        cfg.outputs = list(manual.get("outputs", []) or [])

        api = raw.get("api", {}) or {}
        cfg.api_base = api.get("api_base", cfg.api_base)
        cfg.model_name = api.get("model_name", cfg.model_name)
        cfg.api_max_retries = int(api.get("max_retries", cfg.api_max_retries))
        cfg.api_timeout = int(api.get("timeout", cfg.api_timeout))

        thr = raw.get("threshold", {}) or {}
        cfg.fail_threshold = float(thr.get("fail_threshold", cfg.fail_threshold))
        cfg.use_task_id_threshold = bool(thr.get("use_task_id_threshold", cfg.use_task_id_threshold))
        cfg.task_id_boundary = int(thr.get("task_id_boundary", cfg.task_id_boundary))
        cfg.high_threshold = float(thr.get("high_threshold", cfg.high_threshold))

        cmap = raw.get("category_map")
        if isinstance(cmap, dict) and cmap:
            cfg.category_map = {str(k): str(v) for k, v in cmap.items()}
        return cfg


# ==========================================
#               IO helpers
# ==========================================

def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==========================================
#               LLM API
# ==========================================

def call_llm_api(prompt, cfg: FailAnalysisConfig):
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": cfg.model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    for attempt in range(cfg.api_max_retries):
        try:
            resp = requests.post(
                f"{cfg.api_base}/chat/completions",
                headers=headers, json=payload, timeout=cfg.api_timeout,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt == cfg.api_max_retries - 1:
                print(f"  API Error: {e}")
                return ""
            time.sleep(1.5 ** attempt)
    return ""


def build_prompt(final_memory, error, llm_reasoning=None):
    return (
        "You are an expert in analyzing agent failures. The following is a failed case (it is definitely a failure). "
        "You MUST select at least one failure reason from the categories below (multiple categories are allowed if appropriate):\n\n"
        "1. Parsing Failure: The agent's output could not be parsed (e.g., invalid JSON, missing required fields, or formatting violations).\n"
        "2. Tool Invocation Error: The agent tried to call a tool that doesn't exist, used wrong parameter names, or input values that violated the tool's schema.\n"
        "3. Reasoning Deficit: The agent's format was correct, but it made a logical mistake, chose a wrong path, got stuck in a loop of valid but useless actions, or claimed to solve the problem when it actually didn't.\n"
        "4. Timeout: The log indicates the process was terminated due to a time limit (e.g., \"TimeoutError\", \"Time Limit Exceeded\").\n"
        "5. Iteration Limit Exceeded: The log ends because the agent reached the maximum number of allowed steps (e.g., \"Max turns reached\") without submitting a final answer.\n"
        "6. Context Overflow: The log indicates an error related to token limits (e.g., \"context length exceeded\", \"rate limit due to tokens\").\n\n"
        "Please output a JSON object with two fields:\n"
        "- \"category\": a list of the most likely failure category index/indices (choose from 1-6 above, can be a list if multiple apply, e.g. [2,3])\n"
        "- \"reason\": a brief explanation (in English) for your classification.\n\n"
        "Here is the agent's final memory, error message (if any), and evaluation reasoning:\n\n"
        f"final_memory:\n{json.dumps(final_memory, ensure_ascii=False, indent=2)}\n\n"
        f"error:\n{error if error else ''}\n\n"
        f"llm_reasoning:\n{llm_reasoning if llm_reasoning else ''}\n"
    )


def normalize_categories(cats):
    if cats is None:
        return []
    if isinstance(cats, (int, str)):
        return [cats]
    if isinstance(cats, list):
        return cats
    return [str(cats)]


def update_category_stats(category_stats, cats, category_map):
    for c in normalize_categories(cats):
        c_str = str(c)
        c_name = category_map.get(c_str, c_str)
        category_stats[c_name] = category_stats.get(c_name, 0) + 1


def parse_llm_response(llm_resp):
    """Parse JSON from LLM response, stripping ```json fences."""
    content = (llm_resp or "").strip()
    if content.startswith("```json"):
        content = content[7:].strip()
    elif content.startswith("```"):
        content = content[3:].strip()
    if content.endswith("```"):
        content = content[:-3].strip()

    start = content.find("{")
    end = content.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(content[start:end])
        except Exception as e:
            return {"category": "LLM Error", "reason": f"JSON parse error: {e}"}
    return {"category": "LLM Error", "reason": "No JSON found"}


def get_failure_threshold(task_id, cfg: FailAnalysisConfig):
    if not cfg.use_task_id_threshold:
        return cfg.fail_threshold
    try:
        return cfg.high_threshold if int(task_id) > cfg.task_id_boundary else cfg.fail_threshold
    except Exception:
        return cfg.fail_threshold


# ==========================================
#               Core analysis
# ==========================================

def analyze_single_pair(log_file, eval_file, output_file, cfg: FailAnalysisConfig):
    log_file = Path(log_file)
    eval_file = Path(eval_file)
    output_file = Path(output_file)

    print(f"\nProcessing Pair:\n  Log: {log_file.name}\n  Eval: {eval_file.name}")

    # 1. Load eval results
    if eval_file.suffix == ".jsonl":
        eval_results = list(load_jsonl(eval_file))
    else:
        content = load_json(eval_file)
        eval_results = content.get("results", content) if isinstance(content, dict) else content

    # 2. Filter failures
    failed = []
    for idx, r in enumerate(eval_results):
        try:
            score = float(r.get("score", 0.0))
            task_id = r.get("task_id") or r.get("outer_task_id") or idx
            threshold = get_failure_threshold(task_id, cfg)
            if score < threshold:
                failed.append((idx, r, score, threshold))
        except Exception:
            continue

    if not failed:
        print("  > Skipping: No failed samples found.")
        return

    # 3. Load log file
    log_list = list(load_jsonl(log_file))
    log_map = {str(i): item for i, item in enumerate(log_list)}

    # 4. Resume support: load existing entries
    output_file.parent.mkdir(parents=True, exist_ok=True)

    done_ids = set()
    old_entities = []
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if line_idx == 0 and "category_stats" in obj:
                        continue
                    if "index" in obj:
                        done_ids.add(obj.get("index"))
                        old_entities.append(obj)
                except Exception:
                    pass

    print(f"  > Found {len(failed)} failed cases. Already done {len(done_ids)}. Analyzing...")

    # 5. Per-case analysis
    new_entities = []
    for idx, r, score, threshold in failed:
        if idx in done_ids:
            continue

        log_item = log_map.get(str(idx))
        if not log_item:
            print(f"  Warning: Index {idx} not found in log file.")
            continue

        final_memory = log_item.get("final_memory") or log_item.get("agent_state") or {}
        error = log_item.get("error", "")
        llm_reasoning = r.get("llm_reasoning", "")

        prompt = build_prompt(final_memory, error, llm_reasoning)
        llm_resp = call_llm_api(prompt, cfg)
        analysis = parse_llm_response(llm_resp)

        entity = {
            "index": idx,
            "task_id": str(r.get("task_id") or r.get("outer_task_id") or idx),
            "score": score,
            "failure_threshold": threshold,
            "llm_output": llm_resp,
            "category": analysis.get("category"),
            "reason": analysis.get("reason"),
            "log_file": log_file.name,
            "eval_file": eval_file.name,
        }
        new_entities.append(entity)
        print(f"  [Task {entity['task_id']}] score={score}, threshold={threshold}, category={entity['category']}")

    # 6. Aggregate stats: old + new
    all_entities = old_entities + new_entities
    category_stats = {}
    for entity in all_entities:
        update_category_stats(category_stats, entity.get("category"), cfg.category_map)

    stats_entity = {
        "total_failed_in_eval": len(failed),
        "total_analyzed": len(all_entities),
        "newly_analyzed": len(new_entities),
        "category_stats": category_stats,
    }

    # 7. Rewrite file: header line + one entity per line
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(stats_entity, ensure_ascii=False) + "\n")
        for entity in all_entities:
            f.write(json.dumps(entity, ensure_ascii=False) + "\n")

    print(f"  > Done. Saved to {output_file.name}")
    print(f"  > Stats: {category_stats}")


# ==========================================
#               File-name parsing / matching
# ==========================================

def extract_file_info(filename):
    """
    Parse filename:
      Log Pattern: {Model}_logs_{Timestamp}_{Suffix}.jsonl or {Model}_results_{Timestamp}.jsonl
      Supports timestamps: 20260127_174033 and 20260127174033
    """
    ts_match = re.search(r"(\d{8})_?(\d{6})", filename)
    if ts_match:
        date_part = ts_match.group(1)
        time_part = ts_match.group(2)
        full_ts_clean = date_part + time_part
        full_ts_underscore = date_part + "_" + time_part
    else:
        full_ts_clean = None
        full_ts_underscore = None

    model = None
    if "_logs_" in filename:
        model = filename.split("_logs_")[0]
    elif "_results_" in filename:
        model = filename.split("_results_")[0]

    return model, full_ts_clean, full_ts_underscore


def auto_match_pairs(log_dir, eval_dir):
    log_dir = Path(log_dir)
    eval_dir = Path(eval_dir)

    if not log_dir.exists():
        print(f"Error: Log directory not found: {log_dir}")
        return []
    if not eval_dir.exists():
        print(f"Error: Eval directory not found: {eval_dir}")
        return []

    log_files = list(log_dir.glob("*.jsonl"))
    eval_files = list(eval_dir.glob("*.jsonl"))
    print(f"Found {len(log_files)} logs and {len(eval_files)} evals.")

    matched_pairs = []
    for lf in log_files:
        model_name, ts_clean, ts_underscore = extract_file_info(lf.name)
        if not ts_clean or not model_name:
            print(f"Skipping unrecognized log format: {lf.name}")
            continue

        found_eval = None
        for ef in eval_files:
            if model_name in ef.name and (ts_clean in ef.name or ts_underscore in ef.name):
                found_eval = ef
                break

        if found_eval:
            matched_pairs.append((lf, found_eval))
        else:
            print(f"Warning: No matching eval found for log: {lf.name}")
            print(f"  (Looking for eval containing model='{model_name}' AND timestamp='{ts_clean}')")

    return matched_pairs


# ==========================================
#               Run-mode dispatch
# ==========================================

def run_auto(cfg: FailAnalysisConfig):
    if not cfg.log_dir or not cfg.eval_dir or not cfg.output_dir:
        raise ValueError("auto mode requires auto.log_dir / auto.eval_dir / auto.output_dir in config")
    pairs = auto_match_pairs(cfg.log_dir, cfg.eval_dir)
    print(f"\nSuccessfully matched {len(pairs)} pairs. Starting analysis...\n")
    output_dir = Path(cfg.output_dir)
    for log_f, eval_f in pairs:
        out_f = output_dir / f"fail_analysis_{log_f.name}"
        analyze_single_pair(log_f, eval_f, out_f, cfg)


def run_manual(cfg: FailAnalysisConfig):
    if not (len(cfg.logs) == len(cfg.evals) == len(cfg.outputs)):
        raise ValueError(
            f"manual.logs / manual.evals / manual.outputs length mismatch: "
            f"{len(cfg.logs)}, {len(cfg.evals)}, {len(cfg.outputs)}"
        )
    if not cfg.logs:
        raise ValueError("manual mode requires non-empty manual.logs / manual.evals / manual.outputs")

    for i, (log_path, eval_path, output_path) in enumerate(zip(cfg.logs, cfg.evals, cfg.outputs)):
        print("=" * 80)
        print(f"[{i + 1}/{len(cfg.logs)}] Running fail analysis")
        print(f"log:    {log_path}")
        print(f"eval:   {eval_path}")
        print(f"output: {output_path}")
        print("=" * 80)
        try:
            analyze_single_pair(log_path, eval_path, output_path, cfg)
        except Exception as e:
            print(f"[ERROR] Failed on {eval_path}")
            print(str(e))


def run_cli(cfg: FailAnalysisConfig, args):
    if not (args.log and args.eval and args.output):
        raise ValueError("cli mode requires --log, --eval and --output")
    # Allow CLI to override api/model
    if args.api_base:
        cfg.api_base = args.api_base
    if args.model:
        cfg.model_name = args.model
    analyze_single_pair(args.log, args.eval, args.output, cfg)


# ==========================================
#                    Main
# ==========================================

def parse_args():
    parser = argparse.ArgumentParser(description="Failure analysis driver (config-driven).")
    parser.add_argument("--config", default=DEFAULT_CONFIG_PATH,
                        help=f"Path to YAML config (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--mode", choices=["auto", "manual", "cli"], default=None,
                        help="Override run.mode from the config")
    # cli-mode passthrough (only used when effective mode == 'cli')
    parser.add_argument("--log", help="[cli mode] path to the original log file (jsonl)")
    parser.add_argument("--eval", help="[cli mode] path to the eval result file (jsonl/json)")
    parser.add_argument("--output", help="[cli mode] path to save the fail-analysis result (jsonl)")
    parser.add_argument("--api_base", help="[cli mode] override LLM API base url")
    parser.add_argument("--model", help="[cli mode] override LLM model name")
    return parser.parse_args()


def main():
    args = parse_args()

    config_path = args.config
    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Pass --config <path> or create the default at {DEFAULT_CONFIG_PATH}."
        )
    cfg = FailAnalysisConfig.from_yaml(config_path)

    mode = (args.mode or cfg.mode or "auto").lower().strip()
    print(f"[fail_analysis] config={config_path} mode={mode}")

    if mode == "auto":
        run_auto(cfg)
    elif mode == "manual":
        run_manual(cfg)
    elif mode == "cli":
        run_cli(cfg, args)
    else:
        raise ValueError(f"Unknown mode={mode!r}, expected 'auto' / 'manual' / 'cli'")


if __name__ == "__main__":
    main()
