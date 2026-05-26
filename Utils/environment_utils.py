from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import atexit
import shutil
import tempfile
import yaml

_global_environment_context: Dict[str, Any] = {}
_current_task_environment: Dict[str, Any] = {
    "resources": []
}
_tracked_temp_dirs: set[str] = set()
_GENERIC_LABEL_PREFIXES = (
    "environment_path",
    "env_path",
    "environment_paths",
    "env_paths",
    "environment",
    "environments",
    "database_path",
    "database_paths",
    "database",
    "databases",
)

_FILENAME_LABEL_MAP = {
    "database.sqlite": "database",
    "database.db": "database",
    "init.sql": "init_sql",
    "ops_log.jsonl": "ops_log",
    "db_metrics.jsonl": "db_metrics",
    "trace_log.jsonl": "trace_log",
    "execution_summary.json": "execution_summary",
}


        
def _derive_label_from_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path_obj = Path(path_value)
    parts = [part.lower() for part in path_obj.parts]
    for idx, part in enumerate(parts):
        if part.endswith("bench"):
            prefix = part[:-5] or part
            if idx + 1 < len(parts):
                domain = parts[idx + 1]
                suffix = parts[-1]
                return f"{prefix}_{domain}_{suffix}"
    return None


def _maybe_relabeled_resource(entry: Dict[str, str]) -> Dict[str, str]:
    """If the entry label is generic, derive one from the filename."""
    path_value = entry.get("path")
    original_path = entry.get("original_path") or path_value
    if not path_value and not original_path:
        return entry

    name = Path(original_path or path_value).name.lower()
    label = _FILENAME_LABEL_MAP.get(name)
    if not label and name.endswith((".db", ".sqlite", ".sqlite3")):
        label = "database"

    current_label = entry.get("label")
    is_generic = not current_label or any(current_label.lower().startswith(prefix) for prefix in _GENERIC_LABEL_PREFIXES)

    if label and is_generic:
        entry["label"] = label
        return entry

    derived = _derive_label_from_path(original_path)
    if derived and is_generic:
        entry["label"] = derived

    return entry


def _cleanup_temp_directories() -> None:
    while _tracked_temp_dirs:
        temp_dir = _tracked_temp_dirs.pop()
        shutil.rmtree(temp_dir, ignore_errors=True)


atexit.register(_cleanup_temp_directories)


def normalize_environment_config(config: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    """Normalize environment configuration."""
    env_config = config.get("Environment") or {}
    if not env_config:
        return {
            "type": "none",
            "raw_type": None,
            "path_raw": None,
            "base_path": None,
            "repo_root": repo_root.resolve(),
        }
    raw_type = env_config.get("type", "global")
    normalized_type = (
        str(raw_type).strip().lower().replace("_", "-") if raw_type is not None else "global"
    )

    type_aliases = {
        "global": "global",
        "all": "global",
        "full": "global",
        "per-task": "per-task",
        "per task": "per-task",
        "pertask": "per-task",
        "per-benchmark": "per-task",
        "perbenchmark": "per-task",
        "benchmark": "per-task",
        "by-benchmark": "per-task",
        "none": "none",
        "null": "none",
    }
    
    env_type = type_aliases.get(normalized_type, "global")
    if env_type != normalized_type and normalized_type not in type_aliases:
        print(f"Warning: Unknown Environment.type '{raw_type}', defaulting to 'global'.")
    # Get the path of the environment
    path_raw = env_config.get("path", "./Environment")
    path_candidate: Path | None
    if env_type == "none":
        path_candidate = None
    else:
        path_candidate = Path(path_raw)
        if not path_candidate.is_absolute():
            path_candidate = (repo_root / path_candidate).resolve()
        else:
            path_candidate = path_candidate.resolve()

        if not path_candidate.exists() and path_raw is not None:
            print(f"Warning: Environment path {path_candidate} does not exist.")

    return {
        "type": env_type,
        "raw_type": raw_type,
        "path_raw": path_raw,
        "base_path": path_candidate,
        "repo_root": repo_root.resolve(),
    }


def set_global_environment_context(context: Dict[str, Any]) -> None:
    """Store normalized environment context for global access."""
    _global_environment_context.clear()
    _global_environment_context.update(context)


def get_global_environment_context() -> Dict[str, Any]:
    """Retrieve the normalized global environment context."""
    return dict(_global_environment_context)


def set_task_environment_resources(resources: List[Dict[str, Any]]) -> None:
    """Register the resources associated with the current task."""
    _cleanup_previous_task_resources()
    working_resources = _prepare_resource_copies(resources)
    _current_task_environment["resources"] = working_resources
    # Create a serializable version for JSON output (exclude non-serializable objects like db connections)
    serializable_resources = []
    for entry in working_resources:
        serializable_entry = {}
        for k, v in entry.items():
            if isinstance(v, sqlite3.Connection):
                serializable_entry[k] = f"<sqlite3.Connection: {entry.get('path', 'unknown')}>"
            else:
                serializable_entry[k] = v
        serializable_resources.append(serializable_entry)
    with open('resources.json', 'w') as f:
        json.dump(serializable_resources, f)


def _cleanup_previous_task_resources() -> None:
    # Close any open database connections before clearing resources
    resources = _current_task_environment.get("resources", [])
    for entry in resources:
        if isinstance(entry, dict):
            data = entry.get("data")
            if isinstance(data, sqlite3.Connection):
                try:
                    data.close()
                except Exception:
                    pass  # Ignore errors when closing connections
    _current_task_environment["resources"] = []
    _current_task_environment.pop("temp_dir", None)


def clear_task_environment_modifications() -> None:
    """
    Clear all modifications made to the current task environment.

    This can be useful for resetting the environment state during task execution.
    """
    # Reset all resources to their original state
    _current_task_environment["resources"] = []
    print("[Environment] Cleared task environment modifications.")


def _update_registered_resource(
    *,
    label: Optional[str],
    path: Optional[str],
    data: Any = None,
    data_type: Optional[str] = None,
    load_error: Optional[str] = None,
) -> None:
    """Update the cached resource entry in-place if it matches the label/path."""
    resources = _current_task_environment.get("resources", [])
    for entry in resources:
        if not isinstance(entry, dict):
            continue
        if (label and entry.get("label") == label) or (path and entry.get("path") == path):
            if data is not None:
                entry["data"] = data
            if data_type:
                entry["data_type"] = data_type
            if load_error:
                entry["load_error"] = load_error
            return


def update_environment_resource_data(
    *,
    label: Optional[str] = None,
    path: Optional[str] = None,
    data: Any,
    data_type: Optional[str] = None,
) -> bool:
    """
    Update environment resource data in memory.

    This is the unified interface for all benchmarks to update environment data.
    The updated data will be automatically included in task result archives.

    Args:
        label: Resource label to update
        path: Resource path to update (alternative to label)
        data: New data to store
        data_type: Optional data type hint

    Returns:
        True if resource was found and updated, False otherwise
    """
    if not label and not path:
        return False

    resources = _current_task_environment.get("resources", [])

    for entry in resources:
        if not isinstance(entry, dict):
            continue

        entry_label = entry.get("label")
        entry_path = entry.get("path")

        if (label and entry_label == label) or (path and entry_path == path):
            # Update the data in the resource entry
            entry["data"] = data
            if data_type:
                entry["data_type"] = data_type

            return True

    return False


def create_or_update_environment_resource(
    *,
    label: str,
    data: Any,
    data_type: Optional[str] = None,
    path: Optional[str] = None,
) -> bool:
    """
    Create a new environment resource or update an existing one.

    This is useful for benchmarks that need to create new data during execution
    that should be archived with the task results.

    Args:
        label: Resource label (required for identification)
        data: Data to store
        data_type: Optional data type hint
        path: Optional path for the resource

    Returns:
        True if resource was created/updated successfully
    """
    if not label:
        return False

    resources = _current_task_environment.get("resources", [])

    # Check if resource already exists
    for entry in resources:
        if isinstance(entry, dict) and entry.get("label") == label:
            # Update existing resource
            entry["data"] = data
            if data_type:
                entry["data_type"] = data_type
            if path:
                entry["path"] = path
            break
    else:
        # Create new resource entry
        new_entry = {
            "label": label,
            "data": data,
            "data_type": data_type,
        }
        if path:
            new_entry["path"] = path
        resources.append(new_entry)

    return True


def _load_resource_data(path: Path) -> Any:
    """Load a snapshot of the resource content into memory."""
    if path.is_dir():
        # Load all supported files in the directory and its subdirectories
        bundle = {}
        # Supported file extensions for loading
        supported_extensions = [".json", ".jsonl", ".yaml", ".yml", ".csv", ".txt", ".md", ".log"]

        for ext in supported_extensions:
            for resource_file in path.rglob(f"*{ext}"):
                if resource_file.is_file():
                    # Use relative path with forward slashes, replace extension with empty string
                    relative_path = resource_file.relative_to(path)
                    key = str(relative_path).replace("\\", "/").rsplit(".", 1)[0]
                    try:
                        # Reuse the same loading logic for individual files
                        data = _load_resource_data(resource_file)
                        if data is not None:
                            bundle[key] = data
                    except Exception:
                        # Skip files that can't be loaded
                        continue
        return bundle if bundle else None

    if not path.exists():
        return None

    suffix = path.suffix.lower()

    try:
        if suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
        if suffix in {".yaml", ".yml"}:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        if suffix == ".csv":
            with path.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                return [row for row in reader]
        if suffix in {".txt", ".md", ".log"}:
            return path.read_text(encoding="utf-8")
        if suffix == ".sql":
            return path.read_text(encoding="utf-8")
    except Exception:
        return None

    return None


def load_environment_resource(
    *,
    label: Optional[str] = None,
    suffix: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch an environment resource and return its metadata; load file content into memory when possible.

    Priority:
        1. Use an already-registered resource entry (with in-memory data if present).
        2. Load from the matched path using the common data loader.

    Returns:
        dict with keys: label, path, data (if loadable), original_path (if present)
    """
    resource = get_environment_resource_entry(label=label, suffix=suffix)
    if resource:
        if "data" in resource:
            return dict(resource)
        path_value = resource.get("path")
        if path_value:
            data_snapshot = _load_resource_data(Path(path_value))
            loaded = dict(resource)
            if data_snapshot is not None:
                loaded["data"] = data_snapshot
            return loaded
        return dict(resource)

    path = find_environment_resource(label=label, suffix=suffix)
    if not path:
        return None

    path_obj = Path(path).expanduser().resolve()
    data_snapshot = _load_resource_data(path_obj)
    payload: Dict[str, Any] = {"path": str(path_obj)}
    if label:
        payload["label"] = label
    if data_snapshot is not None:
        payload["data"] = data_snapshot
    return payload


def load_environment_data(*, force_reload: bool = False) -> List[Dict[str, Any]]:
    """
    Ensure all registered environment resources are loaded into memory.

    For each resource:
        - If data already exists and force_reload is False, keep it.
        - If file is SQLite, load a read-only copy into an in-memory database (data_type="sqlite").
        - Otherwise, load file content via _load_resource_data.

    Args:
        force_reload: If True, reload data even if already loaded.

    Returns:
        Updated list of resource entries.
    """
    resources = get_task_environment_resources()
    updated: List[Dict[str, Any]] = []

    for entry in resources:
        if not isinstance(entry, dict):
            continue
        if entry.get("data") is not None and not force_reload:
            updated.append(entry)
            continue

        path_value = entry.get("path")
        if not path_value:
            updated.append(entry)
            continue

        path_obj = Path(path_value).expanduser().resolve()
        if not path_obj.exists():
            updated.append(entry)
            continue

        suffix_lower = path_obj.suffix.lower()
        if suffix_lower in {".db", ".sqlite", ".sqlite3"}:
            # For database files, load into memory so modifications don't affect source file
            # The in-memory connection can be used with conn.cursor()
            try:
                source = sqlite3.connect(f"file:{path_obj}?mode=ro", uri=True)
                mem_conn = sqlite3.connect(":memory:")
                source.backup(mem_conn)
                source.close()
                entry["data"] = mem_conn  # Store in-memory connection object
                entry["data_type"] = "sqlite"
                # Clear any previous load errors
                entry.pop("load_error", None)
                _update_registered_resource(
                    label=entry.get("label"), path=str(path_obj), data=mem_conn, data_type="sqlite"
                )
            except Exception as exc:
                entry["load_error"] = f"Failed to load database into memory: {exc}"
                _update_registered_resource(
                    label=entry.get("label"), path=str(path_obj), load_error=entry["load_error"]
                )
            updated.append(entry)
            continue

        data_snapshot = _load_resource_data(path_obj)
        if data_snapshot is not None:
            entry["data"] = data_snapshot
            # Clear any previous load errors
            entry.pop("load_error", None)
            _update_registered_resource(label=entry.get("label"), path=str(path_obj), data=data_snapshot)
        elif force_reload:
            # If force_reload is True but loading failed, set an error
            entry["load_error"] = "Failed to reload data"
        updated.append(entry)
    return updated


def _prepare_resource_copies(resources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build in-memory snapshots of environment resources without mutating original paths.
    The returned entries preserve the original path and include a 'data' field when loaded.
    """
    if not resources:
        return []

    prepared_resources: List[Dict[str, Any]] = []

    for entry in resources:
        if not isinstance(entry, dict):
            continue

        path_value = entry.get("path")
        prepared = dict(entry)

        if path_value:
            source_path = Path(path_value).expanduser().resolve()
            prepared["path"] = str(source_path)
            prepared.setdefault("original_path", str(source_path))
            if source_path.exists():
                suffix_lower = source_path.suffix.lower()
                if suffix_lower in {".db", ".sqlite", ".sqlite3"}:
                    # For database files, load into memory so modifications don't affect source file
                    # The in-memory connection can be used with conn.cursor()
                    try:
                        source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
                        mem_conn = sqlite3.connect(":memory:")
                        source.backup(mem_conn)
                        source.close()
                        prepared["data"] = mem_conn  # Store in-memory connection object
                        prepared["data_type"] = "sqlite"
                    except Exception as exc:
                        prepared["load_error"] = f"Failed to load database into memory: {exc}"
                else:
                    data_snapshot = _load_resource_data(source_path)
                    if data_snapshot is not None:
                        prepared["data"] = data_snapshot

        prepared_resources.append(_maybe_relabeled_resource(prepared))

    return prepared_resources


def get_task_environment_resources() -> List[Dict[str, Any]]:
    """Return the resources registered for the current task."""
    return list(_current_task_environment.get("resources", []))


def find_environment_resource(
    *,
    label: Optional[str] = None,
    suffix: Optional[str] = None,
) -> Optional[str]:
    """
    Locate a registered environment resource by label or suffix.

    Args:
        label: Exact label to match (case-sensitive).
        suffix: File suffix that the resource path should end with.
    """
    resources = get_task_environment_resources()

    for resource in resources:
        path = resource.get("path")
        resource_label = resource.get("label")
        if not path:
            continue

        if label is not None and resource_label == label:
            return path
        if suffix is not None and path.endswith(suffix):
            return path

    return None


def get_environment_resource_entry(
    *,
    label: Optional[str] = None,
    suffix: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Return the full resource entry (including any loaded data) matching label or suffix.
    """
    resources = get_task_environment_resources()

    for resource in resources:
        path = resource.get("path")
        resource_label = resource.get("label")
        if not path:
            continue

        if label is not None and resource_label == label:
            return resource
        if suffix is not None and path.endswith(suffix):
            return resource

    return None


def _is_directory_resource(resource: Dict[str, Any]) -> bool:
    """Check if the resource was originally loaded from a directory."""
    original_path = resource.get("original_path") or resource.get("path")
    if original_path:
        return Path(original_path).is_dir()
    return False


def _archive_directory_data(bundle: dict, destination_path: Path, original_path: Path) -> None:
    """Archive bundle data preserving the original directory structure."""
    destination_path.mkdir(parents=True, exist_ok=True)

    for key, data in bundle.items():
        # key is relative path without extension, restore original structure
        # Try to find the original file extension
        original_file = None
        for ext in [".json", ".jsonl", ".yaml", ".yml", ".csv", ".txt", ".md", ".log"]:
            candidate = original_path / f"{key}{ext}"
            if candidate.exists():
                original_file = candidate
                break

        if original_file:
            # Use original extension
            file_path = destination_path / f"{key}{original_file.suffix}"
        else:
            # Default to .json
            file_path = destination_path / f"{key}.json"

        file_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if isinstance(data, (dict, list)):
                file_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            elif isinstance(data, str):
                file_path.write_text(data, encoding="utf-8")
            else:
                file_path.write_text(str(data), encoding="utf-8")
        except Exception:
            file_path.write_text(str(data), encoding="utf-8")


def _make_serializable(data: Any) -> Any:
    """Convert complex objects to serializable forms."""
    if isinstance(data, dict):
        return {key: _make_serializable(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_make_serializable(item) for item in data]
    elif isinstance(data, sqlite3.Connection):
        return f"<SQLite connection: {data}>"
    elif hasattr(data, '__dict__'):
        # For custom objects, try to serialize their __dict__
        try:
            return f"<{type(data).__name__}: {data.__dict__}>"
        except:
            return f"<{type(data).__name__}: {str(data)}>"
    else:
        # Try to serialize, if it fails return string representation
        try:
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data)


def _slugify_value(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._-")
    return slug or "resource"


def archive_environment_resources(
    resources: List[Dict[str, Any]],
    base_dir: str | Path,
    *,
    task_identifier: Any,
    model_name: str | None = None,
    timestamp: str | None = None,
) -> Optional[Dict[str, Any]]:
    """
    Persist copies of environment resources and optionally produce an archive snapshot.

    Args:
        resources: List of resource dictionaries with at least a 'path' field.
        base_dir: Destination directory where task subdirectories will be created.
        task_identifier: String/number used to separate task archives.
    """
    if not resources or not base_dir:
        return None
    #加上model_name和时间戳保存方式
    # Use the resources list directly - all resources are archived
    # Resources are updated in-place, so they contain the latest data
    working_resources = list(resources) if resources else []

    base_path = Path(base_dir).expanduser().resolve()
    base_path.mkdir(parents=True, exist_ok=True)

    # Create hierarchical directory structure:
    # {model_name}_{timestamp}/task_{id}/
    # This groups all tasks from the same run under one parent directory
    if timestamp and model_name:
        # Parent directory for the entire run: model_name_timestamp
        run_dir = base_path / f"{model_name}_{timestamp}"
    elif timestamp:
        run_dir = base_path / f"run_{timestamp}"
    elif model_name:
        run_dir = base_path / model_name
    else:
        run_dir = base_path / "environment"

    run_dir.mkdir(parents=True, exist_ok=True)

    # Task subdirectory
    if task_identifier:
        task_slug = _slugify_value(str(task_identifier))
        task_dir = run_dir / f"task_{task_slug}"
    else:
        task_dir = run_dir / "task_unknown"

    task_dir.mkdir(parents=True, exist_ok=True)

    archived_entries: List[Dict[str, str]] = []
    for resource in working_resources:
        if not isinstance(resource, dict):
            continue
        label = resource.get("label") or "resource"
        filename_hint = _slugify_value(label)
        destination_path = task_dir / filename_hint
        suffix = 1
        while destination_path.exists():
            destination_path = task_dir / f"{filename_hint}_{suffix}"
            suffix += 1

        data = resource.get("data")
        source_str = resource.get("path")
        if data is None and source_str:
            source_path = Path(source_str)
            if not source_path.exists():
                continue
            try:
                if source_path.is_file():
                    shutil.copy2(source_path, destination_path)
                elif source_path.is_dir():
                    # Use dirs_exist_ok=True for Python 3.8+ to avoid errors when destination exists
                    shutil.copytree(source_path, destination_path, dirs_exist_ok=True)
                else:
                    continue
            except TypeError:
                # Python < 3.8 doesn't support dirs_exist_ok, fall back to manual copy
                try:
                    if source_path.is_dir():
                        shutil.copytree(source_path, destination_path)
                except FileExistsError:
                    print(f"Warning: Destination already exists, skipping directory copy: {destination_path}")
                    continue
            except Exception as exc:  # pragma: no cover - best effort archival
                print(f"Warning: Failed to archive environment resource {source_path}: {exc}")
                continue
        elif data is not None:
            try:
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(data, sqlite3.Connection):
                    # Persist in-memory database to file
                    conn = data
                    if not destination_path.suffix:
                        destination_path = destination_path.with_suffix(".db")
                    backup = sqlite3.connect(str(destination_path))
                    conn.backup(backup)
                    backup.close()
                elif isinstance(data, str):
                    destination_path.write_text(data, encoding="utf-8")
                elif isinstance(data, dict) and _is_directory_resource(resource):
                    # Handle data from directory - preserve original directory structure
                    original_path = Path(resource.get("original_path") or resource.get("path"))
                    _archive_directory_data(data, destination_path, original_path)
                elif isinstance(data, list) or isinstance(data, dict):
                    try:
                        destination_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    except (TypeError, ValueError) as exc:
                        # If JSON serialization fails, try to convert complex objects
                        try:
                            # Convert complex objects to strings
                            serializable_data = _make_serializable(data)
                            destination_path.write_text(json.dumps(serializable_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        except Exception:
                            # Last resort: save as string representation
                            destination_path.write_text(str(data), encoding="utf-8")
                else:
                    destination_path.write_text(str(data), encoding="utf-8")
            except Exception as exc:  # pragma: no cover - best effort archival
                print(f"Warning: Failed to archive in-memory resource {label}: {exc}")
                continue
        else:
            continue

        archived_entries.append(
            {
                "label": label,
                "source_path": source_str or "",
                "archive_path": str(destination_path.resolve()),
            }
        )

    if not archived_entries:
        return None

    return {
        "task_dir": str(task_dir),
        "resources": archived_entries,
    }


def get_primary_database_path() -> Optional[str]:
    """Deprecated: maintained for backward compatibility; returns None."""
    return None


def _resolve_path_string(path_str: str, environment_context: Dict[str, Any]) -> str:
    """Resolve a possibly-relative path to an absolute path."""
    path_str = path_str.strip()
    if not path_str:
        return ""

    if os.path.isabs(path_str):
        return os.path.abspath(path_str)

    repo_root = environment_context.get("repo_root")
    base_path = environment_context.get("base_path")

    candidates = []
    if repo_root:
        candidates.append(repo_root / path_str)
    if base_path and base_path not in candidates:
        candidates.append(base_path / path_str)

    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate.exists():
            return str(candidate)

    # Fall back to first candidate even if it doesn't exist
    if candidates:
        return str(candidates[0].resolve())

    return os.path.abspath(path_str)


def _resolve_path_from_value(value: Any, environment_context: Dict[str, Any]) -> str:
    """Extract and resolve a path from various value formats."""
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("path", "location", "file"):
            if key in value and isinstance(value[key], str):
                return _resolve_path_string(value[key], environment_context)
        return ""
    if isinstance(value, str):
        return _resolve_path_string(value, environment_context)
    return ""


def _deduplicate_resources(resources: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen = set()
    deduped = []
    for entry in resources:
        path_value = entry.get("path")
        if not path_value:
            continue
        if path_value in seen:
            continue
        seen.add(path_value)
        deduped.append(entry)
    return deduped


def _load_global_environment_resources(environment_context: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Load all environment resources in global mode.
    Scans the environment base path for database files and other resources.
    """
    base_path = environment_context.get("base_path")
    if not base_path:
        return []
    
    base_path = Path(base_path)
    if not base_path.exists() or not base_path.is_dir():
        return []
    
    resources: List[Dict[str, Any]] = []
    
    # Add the root directory as a resource (directory listing only)
    resources.append({"label": "global_environment_root", "path": str(base_path), "data": None})
    
    # Scan for database files (.db, .sqlite, .sqlite3) - RECURSIVELY
    db_extensions = [".db", ".sqlite", ".sqlite3"]
    for ext in db_extensions:
        for db_file in base_path.rglob(f"*{ext}"):  # Changed from glob to rglob for recursive scan
            if db_file.is_file():
                # Use relative path for label to distinguish files in subdirectories
                relative_path = db_file.relative_to(base_path)
                label = f"database_{str(relative_path).replace('/', '_').replace('.', '_')}"
                resources.append(
                    {
                        "label": label,
                        "path": str(db_file.resolve()),
                        "data": None,  # db 数据按需由工具加载到内存
                    }
                )

    # Scan for other common resource files - RECURSIVELY
    resource_extensions = [".json", ".yaml", ".yml", ".csv", ".txt"]
    for ext in resource_extensions:
        for resource_file in base_path.rglob(f"*{ext}"):  # Changed from glob to rglob for recursive scan
            if resource_file.is_file():
                # Use optimized labeling for better readability
                label = _generate_optimized_label(resource_file, base_path)
                resources.append(
                    {
                        "label": label,
                        "path": str(resource_file.resolve()),
                        "data": _load_resource_data(resource_file),
                    }
                )
    
    return _deduplicate_resources(resources)


def extract_task_environment_resources(
    task: Dict[str, Any], environment_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Extract environment resources for a single task when running in per-task mode."""
    if environment_context.get("type") != "per-task":
        return []
    candidate_keys = [
        "environment_path",
        "env_path",
        "environment_paths",
        "env_paths",
        "environment",
        "environments",
        "database_path",
        "database_paths",
        "database_path_abs",
        "database",
        "databases",
    ]

    resources: List[Dict[str, Any]] = []
    found_any_valid_path = False

    for key in candidate_keys:
        if key not in task:
            continue

        value = task[key]
        if isinstance(value, list):
            for idx, item in enumerate(value, start=1):
                resolved = _resolve_path_from_value(item, environment_context)
                if resolved:
                    resolved_path = Path(resolved)

                    # Check if path exists
                    if resolved_path.exists():
                        # 如果是目录，递归发现其中的所有资源文件
                        if resolved_path.is_dir():
                            dir_resources = _extract_directory_resources(resolved_path, environment_context)
                            resources.extend(dir_resources)
                        else:
                            # 如果是文件，直接添加
                            entry = {"label": f"{key}[{idx}]", "path": resolved}
                            resources.append(_maybe_relabeled_resource(entry))
                        found_any_valid_path = True
                    else:
                        # Path doesn't exist - try parent directory
                        parent = resolved_path.parent
                        if parent.exists() and parent.is_dir():
                            print(f"Warning: Path '{resolved}' not found. Using parent directory '{parent}' instead.")
                            dir_resources = _extract_directory_resources(parent, environment_context)
                            resources.extend(dir_resources)
                            found_any_valid_path = True
        else:
            resolved = _resolve_path_from_value(value, environment_context)
            if resolved:
                resolved_path = Path(resolved)

                # Check if path exists
                if resolved_path.exists():
                    # 如果是目录，递归发现其中的所有资源文件
                    if resolved_path.is_dir():
                        dir_resources = _extract_directory_resources(resolved_path, environment_context)
                        resources.extend(dir_resources)
                    else:
                        # 如果是文件，直接添加
                        entry = {"label": key, "path": resolved}
                        resources.append(_maybe_relabeled_resource(entry))
                    found_any_valid_path = True
                else:
                    # Path doesn't exist - try parent directory
                    parent = resolved_path.parent
                    if parent.exists() and parent.is_dir():
                        print(f"Warning: Path '{resolved}' not found. Using parent directory '{parent}' instead.")
                        dir_resources = _extract_directory_resources(parent, environment_context)
                        resources.extend(dir_resources)
                        found_any_valid_path = True

    # If no valid paths found but we have a base_path, fall back to scanning it
    if not found_any_valid_path:
        base_path = environment_context.get("base_path")
        if base_path:
            base_path = Path(base_path)
            if base_path.exists() and base_path.is_dir():
                # 只在任务指定了环境路径但找不到时才警告
                has_env_path_field = any(key in task for key in [
                    "environment_path", "env_path", "environment_paths", "env_paths",
                    "environment", "environments", "database_path", "database_paths"
                ])
                if has_env_path_field:
                    # 静默回退，不打印警告（因为可能有些环境目录确实不存在）
                    #保存
                    # Convert Path objects to strings for JSON serialization
                    serializable_context = {}
                    for key, value in environment_context.items():
                        if isinstance(value, Path):
                            serializable_context[key] = str(value)
                        else:
                            serializable_context[key] = value
                    with open(f"environment_context.json", "w") as f:
                        json.dump(serializable_context, f)
                # Recursively scan for all resource files
                fallback_resources = _load_global_environment_resources(environment_context)
                return fallback_resources

    return _deduplicate_resources(resources)


def _extract_directory_resources(dir_path: Path, environment_context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Extract all resource files from a directory, similar to global mode scanning."""
    resources: List[Dict[str, Any]] = []

    # Scan for database files (.db, .sqlite, .sqlite3) - RECURSIVELY
    db_extensions = [".db", ".sqlite", ".sqlite3"]
    for ext in db_extensions:
        for db_file in dir_path.rglob(f"*{ext}"):
            if db_file.is_file():
                # Use relative path for label to distinguish files in subdirectories
                try:
                    relative_path = db_file.relative_to(dir_path)
                    label = f"database_{str(relative_path).replace('/', '_').replace('.', '_')}"
                except ValueError:
                    # If relative_to fails, use filename
                    label = f"database_{db_file.name.replace('.', '_')}"
                resources.append(
                    {
                        "label": label,
                        "path": str(db_file.resolve()),
                        "data": None,  # db 数据按需由工具加载到内存
                    }
                )

    # Scan for other common resource files - RECURSIVELY
    resource_extensions = [".json", ".jsonl", ".yaml", ".yml", ".csv", ".txt", ".md", ".log"]
    for ext in resource_extensions:
        for resource_file in dir_path.rglob(f"*{ext}"):
            if resource_file.is_file():
                label = _generate_optimized_label(resource_file, dir_path)
                resources.append(
                    {
                        "label": label,
                        "path": str(resource_file.resolve()),
                        "data": _load_resource_data(resource_file),
                    }
                )

    return resources


def _generate_optimized_label(resource_file: Path, dir_path: Path) -> str:
    """Generate an optimized, human-readable label for resource files."""
    try:
        relative_path = resource_file.relative_to(dir_path)
    except ValueError:
        # If relative_to fails, use filename
        filename = resource_file.name
        return filename

    # Get filename without extension
    filename = relative_path.name
    name_without_ext = filename

    # Check if this file is in a recursive folder structure (more than 1 level deep)
    parts = list(relative_path.parts)
    if len(parts) > 2:  # More than 2 parts means nested directories
        # For deeply nested files, use parent_dir_filename format
        parent_dir = parts[-2]  # Immediate parent directory
        return f"{parent_dir}_{name_without_ext}"
    else:
        # For shallow structures, just use filename
        return name_without_ext


def build_task_objective(
    task: Dict[str, Any], environment_context: Dict[str, Any]
) -> Tuple[str, List[Dict[str, Any]]]:
    """Compose the objective string for the agent, enriched with environment information."""
    description_raw = task.get("description") or task.get("task") or task.get("instruction") or str(task)
    if isinstance(description_raw, list):
        description = "\n".join([str(item) for item in description_raw])
    else:
        description = str(description_raw)
    resources: List[Dict[str, Any]] = []

    if environment_context.get("type") == "global":
        resources = _load_global_environment_resources(environment_context)
    else:
        resources = extract_task_environment_resources(task, environment_context)


    return description, resources