from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from Utils.environment_utils import (
    archive_environment_resources,
    build_task_objective,
    get_global_environment_context,
    set_task_environment_resources,
    get_task_environment_resources,
)
from Utils.task_context import clear_current_task, set_current_task
from Utils.result_utils import (
    append_jsonl_record,
    extract_agent_steps,
    extract_final_memory_state,
    get_logs_file_path,
    get_results_file_path,
    load_completed_task_ids,
    load_jsonl_records,
    summarize_steps,
)
from Utils.agent_utils import (
    AgentBundle,
    create_agents_with_tool_map,
)
from smolagents import Tool


def _is_multi_turn_task(task: Dict[str, Any], multi_turn_flag: bool) -> bool:
    if multi_turn_flag:
        return True
    turns = task.get("question")
    if isinstance(turns, list) and turns:
        return True
    instructions = task.get("instruction")
    if isinstance(instructions, list) and len(instructions) > 1:
        return True
    return False


def _stringify_messages(messages: Any) -> str:
    """Render a list of role/content dicts (or raw strings) into a user prompt."""
    if not isinstance(messages, list):
        return str(messages)
    parts = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        else:
            parts.append(str(msg))
    return "\n".join(parts).strip()


def _extract_turn_prompts(task: Dict[str, Any]) -> List[str]:
    turns_raw = task.get("instruction") or task.get("question") or []
    prompts: List[str] = []
    for turn in turns_raw:
        prompts.append(_stringify_messages(turn))
    return prompts


def _model_name_for_runtime(config: Optional[Dict[str, Any]]) -> str:
    if not config:
        return "unknown"
    model_name = _find_model_id(config)
    if not model_name or model_name == "unknown":
        return "unknown"
    return str(model_name).split("/")[-1]


def _build_batch_log_label(
    benchmark_type: str,
    start_idx: Optional[int],
    end_idx: Optional[int],
) -> str:
    label_parts = [benchmark_type or "batch"]
    if start_idx is not None:
        label_parts.append(f"start{start_idx}")
    if end_idx is not None:
        label_parts.append(f"end{end_idx}")
    return "_".join(label_parts)


def run_interactive_mode(agent, environment_context: Dict[str, Any]) -> None:
    """Run the agent in interactive mode."""
    print("\nEntering interactive mode, type 'quit' or 'exit' to exit")
    while True:
        try:
            user_input = input("\nPlease enter a task: ").strip()
            if user_input.lower() in ["quit", "exit"]:
                break
            if not user_input:
                continue

            print(f"\nExecuting task: {user_input}")
            interactive_task = {
                "description": user_input,
                "_runtime_task_id": "interactive",
                "_runtime_model_id": "interactive",
            }
            set_current_task(interactive_task)
            _, resources = build_task_objective(interactive_task, environment_context)
            set_task_environment_resources(resources or _default_global_resources())
            result = agent.run(user_input)
            print(f"\nResult: {result}")

        except KeyboardInterrupt:
            clear_current_task()
            print("\n\nProgram interrupted by user")
            break
        except Exception as exc:
            clear_current_task()
            print(f"\nError executing task: {exc}")
        else:
            clear_current_task()

def run_specific_task(
    agent, task_description: str, environment_context: Dict[str, Any]
) -> Tuple[Any, List[Dict[str, str]], List[Dict[str, Any]], Dict[str, Any]]:
    """Run a single task specified via command line."""
    print(f"Running specific task: {task_description}")
    single_task = {
        "description": task_description,
        "_runtime_task_id": "single",
        "_runtime_model_id": "single",
    }
    set_current_task(single_task)
    try:
        _, env_resources = build_task_objective(single_task, environment_context)
        set_task_environment_resources(env_resources or _default_global_resources())
        result = agent.run(task_description)
        print(f"Result: {result}")
        # Note: managed_agents not available in run_specific_task context
        steps = extract_agent_steps(agent)
        summary = summarize_steps(steps)
        # 返回更新后的资源列表
        current_resources = get_task_environment_resources()
        return result, current_resources, steps, summary
    finally:
        clear_current_task()


def _create_fresh_agent_bundle(
    agent_bundle: AgentBundle,
    tool_map: Optional[Dict[str, Tool]] = None
) -> AgentBundle:
    """Create a fresh agent bundle instance for thread-safe parallel execution."""
    return create_agents_with_tool_map(
        agent_settings=agent_bundle.agent_settings,
        blueprints=agent_bundle.blueprints,
        mode=agent_bundle.mode,
        model=agent_bundle.model,
        tool_map=tool_map if tool_map else agent_bundle.tool_map,
        force_all_tools=True,
    )


def _execute_single_task(
    index: int,
    position: int,
    total_count: int,
    task: Dict[str, Any],
    agent_bundle: AgentBundle,
    agent_cache: Dict[str, Any],
    agent_cache_lock: Lock,
    benchmark_type: str,
    environment_context: Dict[str, Any],
    config: Optional[Dict[str, Any]],
    include_environment: bool,
    archive_enabled: bool,
    archive_dir: Optional[str],
    per_task_tools: bool,
    grouped_tools: Optional[Dict[str, Dict[str, Tool]]],
    retry_attempts: int,
    multi_turn: bool,
    run_timestamp: str,
    parallel_mode: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Execute a single task and return result and log entry.

    Args:
        parallel_mode: If True, creates a fresh agent instance for thread safety.
    """
    env_resources: List[Dict[str, str]] = []
    task_description = task.get("description") or task.get("task") or task.get("instruction") or str(task)
    tool_source = ""
    selected_tool_names: List[str] = []

    # In parallel mode, create a fresh agent for this task to avoid state conflicts
    if parallel_mode:
        if per_task_tools:
            tool_map, tool_source = _select_tools_for_task(task, grouped_tools or {})
            fresh_bundle = _create_fresh_agent_bundle(agent_bundle, tool_map if tool_map else None)
            selected_tool_names = sorted(tool_map.keys()) if tool_map else []
        else:
            fresh_bundle = _create_fresh_agent_bundle(agent_bundle)
        agent = fresh_bundle.primary
        managed_agents = fresh_bundle.managed
    else:
        # Serial mode: use cached agents
        agent = agent_bundle.primary
        managed_agents = agent_bundle.managed

        # Build a task-specific agent when requested (serial mode only, uses cache)
        if per_task_tools:
            tool_map, tool_source = _select_tools_for_task(task, grouped_tools or {})
            cache_key = _cache_key_for_tools(tool_map)

            with agent_cache_lock:
                if cache_key in agent_cache:
                    agent = agent_cache[cache_key]["primary"]
                    managed_agents = agent_cache[cache_key]["managed"]
                    selected_tool_names = agent_cache[cache_key]["tool_names"]
                else:
                    task_bundle = create_agents_with_tool_map(
                        agent_settings=agent_bundle.agent_settings,
                        blueprints=agent_bundle.blueprints,
                        mode=agent_bundle.mode,
                        model=agent_bundle.model,
                        tool_map=tool_map if tool_map else agent_bundle.tool_map,
                        force_all_tools=True,
                    )
                    agent_cache[cache_key] = {
                        "primary": task_bundle.primary,
                        "managed": task_bundle.managed,
                        "tool_names": sorted(tool_map.keys()),
                    }
                    agent = task_bundle.primary
                    managed_agents = task_bundle.managed
                    selected_tool_names = agent_cache[cache_key]["tool_names"]

    if per_task_tools:
        display_source = tool_source or "default"
        display_tools = ", ".join(selected_tool_names) if selected_tool_names else "none"
        print(f"  Tool selection [{display_source}]: {display_tools}")

    attempts = max(1, int(retry_attempts or 1))
    runtime_model_name = _model_name_for_runtime(config)
    runtime_task = dict(task)
    runtime_task["_runtime_task_id"] = index
    runtime_task["_runtime_model_id"] = runtime_model_name
    set_current_task(runtime_task)

    try:
        for attempt in range(1, attempts + 1):
            turn_logs: List[Dict[str, Any]] = []
            try:
                objective, env_resources = build_task_objective(task, environment_context)
                set_task_environment_resources(env_resources or _default_global_resources())

                task_is_multi_turn = _is_multi_turn_task(task, multi_turn)
                if task_is_multi_turn:
                    turn_prompts = _extract_turn_prompts(task)
                    preview = turn_prompts[0] if turn_prompts else task_description
                    print(
                        f"\n[{position}/{total_count}] Executing task #{index} (attempt {attempt}/{attempts}) [multi-turn]: {preview}"
                    )
                else:
                    print(
                        f"\n[{position}/{total_count}] Executing task #{index} (attempt {attempt}/{attempts}): {task_description}"
                    )

                if environment_context.get("type") == "per-task":
                    if env_resources:
                        print("  Resolved environment resources:")
                        for resource in env_resources:
                            print(f"    - {resource['label']}: {resource['path']}")
                    else:
                        print("  Warning: No environment resources resolved for this task.")

                # Prepend Task ID to specific instruction so the agent knows the ID.
                request_prompt = objective or task_description
                if task_is_multi_turn:
                    result = None
                    turn_prompts = turn_prompts if "turn_prompts" in locals() else _extract_turn_prompts(task)
                    if not turn_prompts:
                        turn_prompts = [request_prompt]
                    for turn_idx, prompt in enumerate(turn_prompts, start=1):
                        print(f"  Turn {turn_idx}/{len(turn_prompts)}")
                        result = agent.run(prompt, reset=(turn_idx == 1))
                        turn_logs.append({"turn": turn_idx, "prompt": prompt, "result": str(result)})
                    print(f"Result (final turn): {result}")
                else:
                    result = agent.run(request_prompt)
                    print(f"Result: {result}")

                # Extract steps from all agents (primary + managed)
                steps = extract_agent_steps(agent, managed_agents=managed_agents)
                summary = summarize_steps(steps)

                # Extract final memory state from all agents
                final_memory = extract_final_memory_state(agent, managed_agents=managed_agents)

                archive_metadata = None
                if archive_enabled and archive_dir:
                    current_resources = get_task_environment_resources()

                    # Extract model name for organized archiving
                    model_name = None
                    if config:
                        model_name = _find_model_id(config)
                        if model_name and model_name != "unknown":
                            model_name = model_name.split("/")[-1]

                    archive_metadata = archive_environment_resources(
                        current_resources,
                        archive_dir,
                        task_identifier=index,
                        model_name=model_name,
                        timestamp=run_timestamp,
                    )

                task_result = {
                    "task_id": index,
                    "task": task,
                    "result": str(result),
                    "timestamp": datetime.now().isoformat(),
                    "benchmark_type": benchmark_type,
                    "environment_type": environment_context.get("type"),
                }
                if task_is_multi_turn:
                    task_result["turns"] = turn_logs
                if archive_metadata:
                    task_result["environment_archive"] = archive_metadata
                task_result.update(summary)

                log_entry = {
                    "task_id": index,
                    "task": task,
                    "timestamp": task_result["timestamp"],
                    "status": "success",
                    "result": str(result),
                    "final_memory": final_memory,
                }
                log_entry.update(summary)
                if task_is_multi_turn:
                    log_entry["turns"] = turn_logs
                if archive_metadata:
                    log_entry["environment_archive"] = archive_metadata

                return task_result, log_entry

            except Exception as exc:
                last_error = exc
                if attempt < attempts:
                    print(f"Task {index} attempt {attempt} failed: {exc}. Retrying...")
                    continue

                print(f"Task {index} execution failed after {attempts} attempt(s): {exc}")
                # Extract steps from all agents even on failure
                steps = extract_agent_steps(agent, managed_agents=managed_agents)
                summary = summarize_steps(steps)
                # Extract final memory state
                final_memory = extract_final_memory_state(agent, managed_agents=managed_agents)
                archive_metadata = None
                if archive_enabled and archive_dir:
                    current_resources = get_task_environment_resources()

                    # Extract model name for organized archiving
                    model_name = None
                    if config:
                        model_name = _find_model_id(config)
                        if model_name and model_name != "unknown":
                            model_name = model_name.split("/")[-1]

                    archive_metadata = archive_environment_resources(
                        current_resources,
                        archive_dir,
                        task_identifier=f"{index}_error",
                        model_name=model_name,
                        timestamp=run_timestamp,
                    )

                task_result = {
                    "task_id": index,
                    "task": task,
                    "error": str(exc),
                    "timestamp": datetime.now().isoformat(),
                    "benchmark_type": benchmark_type,
                    "environment_type": environment_context.get("type"),
                }
                if turn_logs:
                    task_result["turns"] = turn_logs
                if include_environment:
                    current_resources = get_task_environment_resources()
                    task_result["environment_resources"] = current_resources
                if archive_metadata:
                    task_result["environment_archive"] = archive_metadata
                task_result.update(summary)

                log_entry = {
                    "task_id": index,
                    "task": task,
                    "timestamp": task_result["timestamp"],
                    "status": "error",
                    "error": str(exc),
                    "final_memory": final_memory,
                }
                log_entry.update(summary)
                if turn_logs:
                    log_entry["turns"] = turn_logs
                if archive_metadata:
                    log_entry["environment_archive"] = archive_metadata

                return task_result, log_entry
    finally:
        clear_current_task()

    # Should not reach here
    raise RuntimeError(f"Task {index} failed unexpectedly")


def run_all_tasks(
    agent_bundle: AgentBundle,
    tasks: List[Dict[str, Any]],
    benchmark_type: str,
    environment_context: Dict[str, Any],
    *,
    config: Optional[Dict[str, Any]] = None,
    include_environment: bool = False,
    archive_enabled: bool = False,
    archive_dir: Optional[str] = None,
    start_idx: Optional[int] = None,
    end_idx: Optional[int] = None,
    per_task_tools: bool = False,
    grouped_tools: Optional[Dict[str, Dict[str, Tool]]] = None,
    retry_attempts: int = 1,
    multi_turn: bool = False,
    run_timestamp: Optional[str] = None,
    max_workers: int = 1,
    realtime_save: bool = True,
    resume_enabled: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    """Run benchmark tasks, optionally within a specific index range.

    Args:
        max_workers: Number of parallel workers (default: 1 for serial execution).
                     Set to > 1 to enable parallel execution.

    Returns:
        Tuple of (results, logs, run_timestamp) where run_timestamp is the unified
        timestamp used for this run (for consistent naming of output/log/environment).
    """
    # Generate unified run_timestamp at the start for consistency across outputs/logs/environment
    if run_timestamp is None:
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not tasks:
        print("No tasks found, please check Benchmark directory or use --interactive mode")
        return [], [], run_timestamp

    total_tasks = len(tasks)
    resolved_start = 1 if not start_idx or start_idx < 1 else start_idx
    resolved_end = total_tasks if not end_idx or end_idx > total_tasks else end_idx

    if resolved_start > resolved_end:
        print(
            f"Invalid task range: start index ({resolved_start}) "
            f"is greater than end index ({resolved_end})."
        )
        return [], [], run_timestamp

    indexed_tasks = [
        (index, task) for index, task in enumerate(tasks, 1) if resolved_start <= index <= resolved_end
    ]

    if not indexed_tasks:
        print(f"No tasks found in the range {resolved_start}-{resolved_end}.")
        return [], [], run_timestamp

    if resolved_start != 1 or resolved_end != total_tasks:
        print(
            f"Found {total_tasks} tasks in total; executing range {resolved_start}-{resolved_end} "
            f"({len(indexed_tasks)} tasks)."
        )
    else:
        print(f"Found {total_tasks} tasks, starting execution...")

    if max_workers > 1:
        print(f"Parallel execution enabled with {max_workers} workers")

    results_file = None
    logs_file = None
    completed_task_ids = set()
    all_results: List[Dict[str, Any]] = []
    all_logs: List[Dict[str, Any]] = []

    if config:
        results_file = get_results_file_path(config, timestamp=run_timestamp)
        logs_file = get_logs_file_path(
            config,
            label=_build_batch_log_label(benchmark_type, start_idx, end_idx),
            timestamp=run_timestamp,
        )

        if resume_enabled:
            all_results = load_jsonl_records(results_file)
            all_logs = load_jsonl_records(logs_file)
            completed_task_ids = load_completed_task_ids(results_file, logs_file)
            if completed_task_ids:
                print(
                    f"Resume enabled: detected {len(completed_task_ids)} completed task(s) "
                    f"from existing outputs/logs."
                )

    if completed_task_ids:
        indexed_tasks = [
            (index, task) for index, task in indexed_tasks if index not in completed_task_ids
        ]
        if not indexed_tasks:
            print("All selected tasks are already completed. Nothing to run.")
            all_results.sort(key=lambda x: x.get("task_id", 0))
            all_logs.sort(key=lambda x: x.get("task_id", 0))
            return all_results, all_logs, run_timestamp
        print(f"Remaining tasks to execute after resume filtering: {len(indexed_tasks)}")

    # Cache agents per tool signature to avoid rebuilding unnecessarily.
    agent_cache: Dict[str, Any] = {}
    agent_cache_lock = Lock()

    persist_lock = Lock()

    def _persist_task_outputs(task_result: Dict[str, Any], log_entry: Dict[str, Any]) -> None:
        all_results.append(task_result)
        all_logs.append(log_entry)
        if realtime_save and results_file and logs_file:
            result_record = dict(task_result)
            result_record.setdefault("saved_at", datetime.now().isoformat())
            append_jsonl_record(results_file, result_record)

            log_record = dict(log_entry)
            log_record.setdefault("saved_at", datetime.now().isoformat())
            append_jsonl_record(logs_file, log_record)

    # Execute tasks based on max_workers setting
    if max_workers == 1:
        # Serial execution (original behavior, uses agent cache for efficiency)
        for position, (index, task) in enumerate(indexed_tasks, 1):
            task_result, log_entry = _execute_single_task(
                index=index,
                position=position,
                total_count=len(indexed_tasks),
                task=task,
                agent_bundle=agent_bundle,
                agent_cache=agent_cache,
                agent_cache_lock=agent_cache_lock,
                benchmark_type=benchmark_type,
                environment_context=environment_context,
                config=config,
                include_environment=include_environment,
                archive_enabled=archive_enabled,
                archive_dir=archive_dir,
                per_task_tools=per_task_tools,
                grouped_tools=grouped_tools,
                retry_attempts=retry_attempts,
                multi_turn=multi_turn,
                run_timestamp=run_timestamp,
                parallel_mode=False,
            )
            _persist_task_outputs(task_result, log_entry)
    else:
        # Parallel execution with ThreadPoolExecutor
        # Each task creates a fresh agent instance for thread safety
        completed_count = 0
        results_lock = Lock()

        print(f"Note: Parallel mode creates fresh agent instances for each task to ensure thread safety.")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {}
            for position, (index, task) in enumerate(indexed_tasks, 1):
                future = executor.submit(
                    _execute_single_task,
                    index=index,
                    position=position,
                    total_count=len(indexed_tasks),
                    task=task,
                    agent_bundle=agent_bundle,
                    agent_cache=agent_cache,
                    agent_cache_lock=agent_cache_lock,
                    benchmark_type=benchmark_type,
                    environment_context=environment_context,
                    config=config,
                    include_environment=include_environment,
                    archive_enabled=archive_enabled,
                    archive_dir=archive_dir,
                    per_task_tools=per_task_tools,
                    grouped_tools=grouped_tools,
                    retry_attempts=retry_attempts,
                    multi_turn=multi_turn,
                    run_timestamp=run_timestamp,
                    parallel_mode=True,
                )
                future_to_task[future] = (index, position)

            # Collect results as they complete
            for future in as_completed(future_to_task):
                index, position = future_to_task[future]
                try:
                    task_result, log_entry = future.result()
                    with results_lock:
                        with persist_lock:
                            _persist_task_outputs(task_result, log_entry)
                        completed_count += 1
                        print(f"Progress: {completed_count}/{len(indexed_tasks)} tasks completed")
                except Exception as exc:
                    print(f"Task #{index} generated an exception: {exc}")
                    # Still append error result
                    with results_lock:
                        completed_count += 1

    # Sort results and logs by task_id to maintain order
    all_results.sort(key=lambda x: x.get("task_id", 0))
    all_logs.sort(key=lambda x: x.get("task_id", 0))

    successful = len([record for record in all_results if "error" not in record])
    failed = len(all_results) - successful
    print(f"\nExecution completed: {successful} successful, {failed} failed")
    return all_results, all_logs, run_timestamp


def _default_global_resources() -> List[Dict[str, str]]:
    """Fallback resources built from the global environment context."""
    global_context = get_global_environment_context()
    base_path = global_context.get("base_path")
    if base_path:
        return [{"label": "global_environment_root", "path": str(base_path)}]
    return []


def _select_tools_for_task(task: Dict[str, Any], grouped_tools: Dict[str, Dict[str, Tool]]) -> tuple[Dict[str, Tool], str]:
    """Pick tools for a task based on its source dataset and requested tool names."""
    dataset = task.get("_dataset") or task.get("_source_file")
    tool_pool = grouped_tools.get(dataset, {})
    source_label = str(dataset) if dataset else ""
    if not tool_pool and isinstance(dataset, str):
        # If dataset was a path, try stem.
        from pathlib import Path

        dataset_stem = Path(dataset).stem
        tool_pool = grouped_tools.get(dataset_stem, {})
        if tool_pool:
            source_label = dataset_stem

    requested = _extract_requested_tool_names(task)
    if tool_pool:
        if not requested:
            return dict(tool_pool), source_label
        selected: Dict[str, Tool] = {}
        for name in requested:
            tool = tool_pool.get(name)
            if tool:
                selected[name] = tool
        return selected or dict(tool_pool), source_label

    # Fallback: if no dataset match, pick the group covering most requested tools.
    if requested and grouped_tools:
        best_group = None
        best_hits = 0
        for group_name, pool in grouped_tools.items():
            hits = sum(1 for name in requested if name in pool)
            if hits > best_hits:
                best_hits = hits
                best_group = group_name
        if best_group and best_hits > 0:
            pool = grouped_tools[best_group]
            selected = {name: pool[name] for name in requested if name in pool}
            return selected or dict(pool), best_group

    return {}, source_label


def _extract_requested_tool_names(task: Dict[str, Any]) -> List[str]:
    """Extract tool names from task metadata (label or explicit tools)."""
    names: List[str] = []
    if isinstance(task.get("tools"), list):
        names.extend(str(item) for item in task["tools"] if item)

    labels = task.get("label") or task.get("labels")
    if labels:
        import re

        label_list = labels if isinstance(labels, list) else [labels]
        for label in label_list:
            if not isinstance(label, str):
                continue
            func_match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(", label)
            if func_match:
                names.append(func_match.group(1))

    seen = set()
    deduped: List[str] = []
    for name in names:
        if name not in seen:
            deduped.append(name)
            seen.add(name)
    return deduped


def _cache_key_for_tools(tool_map: Dict[str, Tool]) -> str:
    if not tool_map:
        return "default"
    return "|".join(sorted(tool_map.keys()))


def _find_model_id(obj: Any) -> Optional[str]:
    """Recursively search for model_id field in config."""
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
