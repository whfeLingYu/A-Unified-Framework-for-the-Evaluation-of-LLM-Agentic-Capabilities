from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

def extract_agent_steps(
    agent: Any,
    *,
    managed_agents: List[Any] | None = None
) -> List[Dict[str, Any]]:
    """
    Extract step history from agent(s), automatically removing memory from individual steps.

    Memory information is removed from each step to reduce redundancy.
    Use extract_final_memory_state() to get the final memory snapshot.

    Args:
        agent: Primary agent to extract steps from
        managed_agents: Optional list of managed agents to also extract steps from

    Returns:
        List of step dictionaries with agent_label, memory fields removed
    """
    if agent is None:
        return []

    def _best_effort_memory_steps(memory_obj: Any) -> List[Dict[str, Any]]:
        """Fallback serializer that does not rely on get_full_steps."""
        raw_steps = getattr(memory_obj, "steps", None)
        if not raw_steps:
            return []

        serialized: List[Dict[str, Any]] = []
        for entry in raw_steps:
            if hasattr(entry, "dict") and callable(getattr(entry, "dict")):
                try:
                    serialized.append(entry.dict())
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    serialized.append({"error": "serialize_failed", "detail": str(exc), "repr": repr(entry)})
                    continue
            if isinstance(entry, dict):
                serialized.append(entry)
            else:
                serialized.append({"value": repr(entry)})
        return serialized

    def _extract_single_agent_steps(single_agent: Any, agent_label: str = "primary") -> List[Dict[str, Any]]:
        """Extract steps from a single agent."""
        candidate = None
        errors: List[str] = []

        if hasattr(single_agent, "get_full_steps") and callable(getattr(single_agent, "get_full_steps")):
            try:
                candidate = single_agent.get_full_steps()
            except Exception as exc:
                errors.append(f"agent.get_full_steps failed: {exc}")
                candidate = None

        if candidate is None and getattr(single_agent, "memory", None) is not None:
            memory = getattr(single_agent, "memory")
            if hasattr(memory, "get_full_steps") and callable(memory.get_full_steps):
                try:
                    candidate = memory.get_full_steps()
                except Exception as exc:
                    errors.append(f"memory.get_full_steps failed: {exc}")
                    candidate = None
            if candidate is None:
                candidate = _best_effort_memory_steps(memory)

        if candidate is None:
            if errors:
                print(f"Warning: unable to extract {agent_label} agent steps ({' | '.join(errors)})")
            return []

        steps = []
        if isinstance(candidate, list):
            steps = candidate
        elif isinstance(candidate, Sequence):
            steps = list(candidate)

        # Add agent label and remove memory from each step
        labeled_steps = []
        for step in steps:
            if isinstance(step, dict):
                step_copy = dict(step)
                step_copy["agent_label"] = agent_label

                # Always strip memory from individual steps (use final_memory instead)
                if "memory" in step_copy:
                    del step_copy["memory"]

                labeled_steps.append(step_copy)
            else:
                labeled_steps.append({"value": repr(step), "agent_label": agent_label})

        return labeled_steps
    agent_name = getattr(agent, "name", None) or f"primary"
    # Extract primary agent steps
    all_steps = _extract_single_agent_steps(agent, agent_name)

    # Extract managed agents steps
    if managed_agents:
        for idx, managed_agent in enumerate(managed_agents):
            if managed_agent is not None:
                agent_name = getattr(managed_agent, "name", None) or f"managed_{idx}"
                managed_steps = _extract_single_agent_steps(managed_agent, agent_name)
                all_steps.extend(managed_steps)

    return all_steps




def extract_final_memory_state(
    agent: Any,
    *,
    managed_agents: List[Any] | None = None
) -> Dict[str, Any]:
    """
    Extract a clean, readable sequence of events (interaction history) from agents.
    Removes redundancy and raw API metadata.
    """
    memory_states = {}

    def _clean_tool_args(args: Any) -> Any:
        """Helper to parse JSON strings in arguments or return as is."""
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return args
        return args

    def _extract_single_agent_history(single_agent: Any) -> List[Dict[str, Any]]:
        """
        Generates a linear history of: User Task -> [Thought -> Call -> Result] -> Final Answer.
        """
        if single_agent is None:
            return []
        
        memory = getattr(single_agent, "memory", None)
        raw_steps = getattr(memory, "steps", []) if memory else []

        clean_history = []
#先不保存system_prompt
        # system_prompt_step = getattr(memory, "system_prompt", None) if memory else None
        # system_prompt_text = getattr(system_prompt_step, "system_prompt", None)
        # if system_prompt_text:
        #     clean_history.append({
        #         "role": "system",
        #         "content": system_prompt_text,
        #     })

        # if not raw_steps:
        #     return clean_history

        # 1. Get the Initial Task / System Prompt if available
        # Some agents store the task in the first step or a specific attribute
        task = getattr(single_agent, "task", None)
        if not task and len(raw_steps) > 0:
            # Try to find the first user message in the first step's input
            first_step = raw_steps[0]
            if hasattr(first_step, "dict"): first_step = first_step.dict()
            messages = first_step.get("model_input_messages", [])
            for msg in messages:
                if msg.get("role") == "user":
                    clean_history.append({
                        "role": "user", 
                        "content": msg.get("content")
                    })
                    break
        elif task:
            clean_history.append({"role": "user", "content": task})

        # 2. Iterate through steps to build the Execution History
        for i, step in enumerate(raw_steps):
            step_data = step.dict() if hasattr(step, "dict") else step

            # --- A. Assistant's Thought / Text Output ---
            # smolagents often puts the thought/reasoning in model_output
            model_output = step_data.get("model_output")
            if model_output:
                clean_history.append({
                    "step": i,
                    "role": "assistant",
                    "type": "thought_or_message",
                    "content": model_output
                })

            # --- B. Tool Calls ---
            tool_calls = step_data.get("tool_calls", [])
            if tool_calls:
                cleaned_calls = []
                for call in tool_calls:
                    # Handle both object and dict formats
                    call_obj = call.dict() if hasattr(call, "dict") else call

                    # Extract function info, supporting different structures
                    func_info = call_obj.get("function", {})
                    if not func_info and "name" in call_obj:
                         # Sometimes call_obj is flat
                         func_info = call_obj

                    cleaned_calls.append({
                        "name": func_info.get("name"),
                        "arguments": _clean_tool_args(func_info.get("arguments"))
                    })

                if cleaned_calls:
                    clean_history.append({
                        "step": i,
                        "role": "assistant",
                        "type": "tool_calls",
                        "content": cleaned_calls
                    })

            # --- C. Observations (Tool Outputs) ---
            observations = step_data.get("observations")
            if observations:
                clean_history.append({
                    "step": i,
                    "role": "tool",
                    "type": "observation",
                    "content": observations
                })

            # --- D. Images (Optional) ---
            images = step_data.get("observations_images")
            if images:
                clean_history.append({
                    "step": i,
                    "role": "tool",
                    "type": "images",
                    "count": len(images),
                    "info": "Images received but not rendered in text log."
                })

            # --- E. Errors ---
            error = step_data.get("error")
            if error:
                clean_history.append({
                    "step": i,
                    "role": "error",
                    "type": "error",
                    "content": error
                })

        return clean_history

    def _get_total_steps(history):
        """Get the total number of steps from history by finding the last step number."""
        for event in reversed(history):
            if "step" in event:
                return event["step"]
        return 0

    # Extract primary agent
    agent_name = getattr(agent, "name", None) or "primary"
    primary_history = _extract_single_agent_history(agent)
    if primary_history:
        total_steps = _get_total_steps(primary_history)
        memory_states[agent_name] = {
            "conversation_summary": primary_history,
            "total_steps": total_steps
        }

    # Extract managed agents
    if managed_agents:
        for idx, managed_agent in enumerate(managed_agents):
            if managed_agent is not None:
                sub_name = getattr(managed_agent, "name", None) or f"managed_{idx}"
                sub_history = _extract_single_agent_history(managed_agent)
                if sub_history:
                    total_steps = _get_total_steps(sub_history)
                    memory_states[sub_name] = {
                        "conversation_summary": sub_history,
                        "total_steps": total_steps
                    }

    return memory_states

def summarize_steps(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate statistics from a list of agent steps."""


    # Group steps by agent for per-agent statistics
    agent_steps = {}
    for step in steps:
        if isinstance(step, dict):
            agent_label = step.get("agent_label", "unknown")
            if agent_label not in agent_steps:
                agent_steps[agent_label] = []
            agent_steps[agent_label].append(step)

    # Calculate per-agent step counts
    per_agent_counts = {}
    for agent_label, agent_step_list in agent_steps.items():
        # Find the maximum step number for this agent (not just len)
        max_step_num = 0
        for step in agent_step_list:
            if "step_number" in step and isinstance(step["step_number"], int):
                max_step_num = max(max_step_num, step["step_number"])
        per_agent_counts[agent_label] = max_step_num if max_step_num > 0 else len(agent_step_list)

    # Calculate total statistics
    total_input_tokens = None
    total_output_tokens = None

    for step in steps:
        usage = step.get("token_usage") if isinstance(step, dict) else None
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            if isinstance(input_tokens, (int, float)):
                total_input_tokens = (total_input_tokens or 0) + int(input_tokens)
            if isinstance(output_tokens, (int, float)):
                total_output_tokens = (total_output_tokens or 0) + int(output_tokens)

    total_tokens = None
    if total_input_tokens is not None or total_output_tokens is not None:
        total_tokens = (total_input_tokens or 0) + (total_output_tokens or 0)

    min_start = None
    max_end = None
    for step in steps:
        timing = step.get("timing") if isinstance(step, dict) else None
        if isinstance(timing, dict):
            start = timing.get("start_time")
            end = timing.get("end_time")
            if isinstance(start, (int, float)):
                min_start = start if min_start is None else min(min_start, start)
            if isinstance(end, (int, float)):
                max_end = end if max_end is None else max(max_end, end)

    elapsed_seconds = None
    if min_start is not None and max_end is not None:
        elapsed_seconds = float(max_end - min_start)
        if elapsed_seconds < 0:
            elapsed_seconds = None
    # Calculate total step count as sum of all agent step counts
    total_step_count = sum(per_agent_counts.values())

    result = {
        "total_step_count": total_step_count,  # Sum of all agent step counts
        "per_agent_step_counts": per_agent_counts,  # Actual step counts per agent
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
    }


    return result


def _normalize_records(records: Any) -> List[Dict[str, Any]]:
    if records is None:
        return []
    if isinstance(records, list):
        normalized = []
        for entry in records:
            if isinstance(entry, dict):
                normalized.append(entry)
            else:
                normalized.append({"value": entry})
        return normalized
    if isinstance(records, dict):
        return [records]
    return [{"value": records}]


def _find_model_id(obj: Any) -> str | None:
    if isinstance(obj, dict):
        if "model_id" in obj:
            return obj["model_id"]
        for value in obj.values():
            result = _find_model_id(value)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_model_id(item)
            if result:
                return result
    return None


def get_model_name(config: Dict[str, Any]) -> str:
    model_id = _find_model_id(config) or "unknown"
    return model_id.split("/")[-1] if model_id != "unknown" else "unknown"


def get_results_file_path(
    config: Dict[str, Any],
    *,
    timestamp: str | None = None,
) -> str:
    output_config = config.get("Output", {})
    save_dir = output_config.get("save_dir", "./results/outputs")
    os.makedirs(save_dir, exist_ok=True)
    resolved_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = get_model_name(config)
    return os.path.join(save_dir, f"{model_name}_results_{resolved_timestamp}.jsonl")


def _slugify_label(label: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", label).strip("._-")
    return slug or "log"


def get_logs_file_path(
    config: Dict[str, Any],
    *,
    label: str | None = None,
    timestamp: str | None = None,
) -> str:
    output_config = config.get("Output", {})
    log_dir = output_config.get("log_dir", "./results/logs")
    os.makedirs(log_dir, exist_ok=True)
    resolved_timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = get_model_name(config)
    filename_parts = [model_name, "logs", resolved_timestamp]
    if label:
        filename_parts.append(_slugify_label(label))
    return os.path.join(log_dir, "_".join(filename_parts) + ".jsonl")


def load_jsonl_records(path: str | os.PathLike[str] | None) -> List[Dict[str, Any]]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        return []

    records: List[Dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Warning: failed to parse JSONL record at {file_path}:{line_number}: {exc}")
                continue
            if isinstance(record, dict):
                records.append(record)
            else:
                records.append({"value": record})
    return records


def append_jsonl_record(path: str | os.PathLike[str], record: Dict[str, Any]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def load_completed_task_ids(*paths: str | os.PathLike[str] | None) -> Set[int]:
    completed: Set[int] = set()
    for path in paths:
        for record in load_jsonl_records(path):
            task_id = record.get("task_id")
            if isinstance(task_id, int):
                completed.add(task_id)
    return completed


def save_results(config: Dict[str, Any], results: Any, *, timestamp: str | None = None) -> str:
    """Save results to the specified directory in JSONL format.

    Args:
        config: Global configuration dictionary.
        results: Results to save.
        timestamp: Optional timestamp string to use for filename. If not provided,
                   generates a new timestamp.
    """
    results_file = get_results_file_path(config, timestamp=timestamp)
    saved_at = datetime.now().isoformat()

    items = _normalize_records(results)
    with open(results_file, "w", encoding="utf-8") as file:
        for item in items:
            record = dict(item)
            record.setdefault("saved_at", saved_at)
            file.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"Results saved to: {results_file}")
    return results_file
def save_logs(
    config: Dict[str, Any],
    logs: Any | None = None,
    agent: Any | None = None,
    label: str | None = None,
    *,
    managed_agents: List[Any] | None = None,
    save_detailed_steps: bool = False,
    timestamp: str | None = None,
) -> str:
    """
    Persist agent execution logs to disk.

    Automatically includes final_memory state from all agents.
    By default, only saves summary statistics and final memory (not detailed steps).

    Args:
        config: Global configuration dictionary.
        logs: Preformatted log payload that includes agent steps (list/dict). If omitted,
            the function attempts to extract steps from the provided agent.
        agent: Agent instance used to extract steps when `logs` is None.
        label: Optional label appended to the log filename for easier identification.
        managed_agents: Optional list of managed agents to extract steps from.
        save_detailed_steps: If False (default), only save summary and final_memory.
                             If True, save full step details.
        timestamp: Optional timestamp string to use for filename. If not provided,
                   generates a new timestamp.
    """
    output_config = config.get("Output", {})

    # Check if config overrides save_detailed_steps
    if not save_detailed_steps:
        save_detailed_steps = output_config.get("save_detailed_steps", False)

    if logs is None and agent is not None:
        steps = extract_agent_steps(agent, managed_agents=managed_agents)
        summary = summarize_steps(steps)
        entry = {**summary, "timestamp": datetime.now().isoformat()}

        # Include detailed steps if requested
        if save_detailed_steps:
            entry["steps"] = steps

        # Always add final memory state
        final_memory = extract_final_memory_state(agent, managed_agents=managed_agents)
        if final_memory:
            entry["final_memory"] = final_memory

        logs = [entry]
    log_file = get_logs_file_path(config, label=label, timestamp=timestamp)

    items = _normalize_records(logs)
    saved_at = datetime.now().isoformat()

    with open(log_file, "w", encoding="utf-8") as file:
        for item in items:
            record = dict(item)
            record.setdefault("saved_at", saved_at)
            # Don't save label - it's redundant and not useful

            # Backfill summary and final_memory when needed
            if agent is not None and len(items) == 1:
                # Add summary if not present
                if "step_count" not in record and "total_tokens" not in record:
                    agent_steps_cache = extract_agent_steps(agent, managed_agents=managed_agents)
                    agent_summary_cache = summarize_steps(agent_steps_cache)
                    for key, value in agent_summary_cache.items():
                        record.setdefault(key, value)

                    # Add detailed steps only if requested
                    if save_detailed_steps and not record.get("steps"):
                        record["steps"] = agent_steps_cache

                # Always add final memory if not present
                if not record.get("final_memory"):
                    final_memory = extract_final_memory_state(agent, managed_agents=managed_agents)
                    if final_memory:
                        record["final_memory"] = final_memory

            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    print(f"Logs saved to: {log_file}")
    return log_file
