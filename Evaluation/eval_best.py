#!/usr/bin/env python3
"""
Refactored Evaluation Script for Agent Sandbox (Tau2 Compatible).
Focus: Robust Path Resolution, Sandboxing, and Structured Action Support.
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import traceback
import glob
import requests
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time
try:
    import openai
except ImportError:
    print("Warning: openai package not found. Please install with: pip install openai")
    openai = None


# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from Utils.benchmark_utils import load_benchmark_tasks
from Utils.config_utils import read_config
from Utils.environment_utils import (
    archive_environment_resources,
    build_task_objective,
    get_global_environment_context,
    set_task_environment_resources,
    get_task_environment_resources,
    set_global_environment_context,
    normalize_environment_config,
)
from Utils.tool_utils import load_tools

# =============================================================================
#  Hashing & File System Utilities
# =============================================================================

MAX_ENVIRONMENT_PROMPT_CHARS = 40000

class HashCompute:
    @staticmethod
    def file_hash(file_path: Path) -> str:
        if not file_path.exists() or not file_path.is_file():
            return ""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                hasher.update(f.read())
        except Exception as e:
            return f"error:{str(e)}"
        return hasher.hexdigest()

    @staticmethod
    def compute_content_hash(file_path: Path) -> str:
        """
        Computes hash of file content. 
        Tries to read as UTF-8 text and STRIPS ALL WHITESPACE (spaces, newlines, indents)
        to ensure 'content' identity is robust against formatting differences.
        Falls back to binary hash for non-text files.
        """
        if not file_path.exists() or not file_path.is_file():
            return ""
        hasher = hashlib.sha256()
        try:
            # Try as text first
            content = file_path.read_text(encoding="utf-8")
            
            # Normalize content by removing ALL whitespace characters
            import re
            clean_content = re.sub(r'\s+', '', content)
            
            hasher.update(clean_content.encode("utf-8"))
        except UnicodeDecodeError:
            # Binary fallback for non-text files
            try:
                hasher.update(file_path.read_bytes())
            except Exception as e:
                return f"error:{str(e)}"
        except Exception as e:
            return f"error:{str(e)}"
        return hasher.hexdigest()

    @staticmethod
    def _aggregate_hash_from_map(file_map: Dict[str, str]) -> str:
        """Helper to produce a deterministic hash from a dictionary of filename->filehash."""
        master_hasher = hashlib.sha256()
        # Ensure strict string-based sorting of keys for consistency across methods
        for k in sorted(file_map.keys()):
            # k is relative path string
            master_hasher.update(k.encode())
            # value is the file hash (or 'missing')
            master_hasher.update(file_map[k].encode())
        return master_hasher.hexdigest()

    @staticmethod
    def directory_hash(dir_path: Path) -> str:
        if not dir_path.exists():
            return ""
        
        file_map = HashCompute.compute_file_hashes_from_dir(dir_path)
        return HashCompute._aggregate_hash_from_map(file_map)

    @staticmethod
    def compute_file_hashes_from_dir(dir_path: Path) -> Dict[str, str]:
        """Returns {rel_path: sha256} for all files in dir."""
        if not dir_path.exists():
            return {}
        file_map = {}
        for file_path in sorted(dir_path.rglob("*")):
            if file_path.is_file():
                try:
                    rel_path = str(file_path.relative_to(dir_path))
                    file_map[rel_path] = HashCompute.file_hash(file_path)
                except: pass
        return file_map

    @staticmethod
    def compute_aligned_hash_files(source_dir: Path, target_dir: Path) -> Dict[str, str]:
        """
        Computes hashes for files in source_dir, looking for corresponding files in target_dir.
        Returns a dict of relative_path -> hash. 
        If corresponding file missing in target, it affects hash.
        """
        file_hashes = {}
        if not source_dir.exists():
            return {}
            
        # Iterate source files to determine what SHOULD be there
        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                try:
                    rel_path = file_path.relative_to(source_dir)
                    target_file = target_dir / rel_path
                    
                    if target_file.exists() and target_file.is_file():
                        file_hashes[str(rel_path)] = HashCompute.file_hash(target_file)
                    else:
                        file_hashes[str(rel_path)] = "missing"
                except Exception as e:
                    file_hashes[str(rel_path)] = f"error:{e}"
        return file_hashes
        
    @staticmethod
    def compute_active_env_hash(env_resources: List[Dict[str, Any]]) -> str:
        master_hasher = hashlib.sha256()
        valid_res_count = 0
        for res in sorted(env_resources, key=lambda x: str(x.get("path", ""))):
            path_str = res.get("path")
            if not path_str: continue
            
            p = Path(path_str)
            if p.exists():
                valid_res_count += 1
                if p.is_file():
                    master_hasher.update(HashCompute.file_hash(p).encode())
                elif p.is_dir():
                    master_hasher.update(HashCompute.directory_hash(p).encode())
            else:
                master_hasher.update(f"missing:{path_str}".encode())
        
        if valid_res_count == 0:
            return ""
        return master_hasher.hexdigest()

    @staticmethod
    def compute_archive_hash(clean_log: Dict[str, Any], archive_dir_override: Optional[str] = None, source_dir_override: Optional[str] = None) -> str:
        """
        Computes hash of the archived environment.
        If source_dir_override AND archive_dir_override is provided, it aligns files.
        Otherwise falls back to recursive archive hash.
        """
        if archive_dir_override and source_dir_override:
             # Aligned hash computation
             arch_path = Path(archive_dir_override)
             src_path = Path(source_dir_override)
             if arch_path.exists() and src_path.exists():
                 aligned_map = HashCompute.compute_aligned_hash_files(src_path, arch_path)
                 return HashCompute._aggregate_hash_from_map(aligned_map)

        if archive_dir_override:
            p = Path(archive_dir_override)
            if p.exists() and p.is_dir():
                return HashCompute.directory_hash(p)
            return ""

        archive_paths = clean_log.get("archive_resource_paths", [])
        if not archive_paths:
            arch_info = clean_log.get("environment_archive", {})
            if arch_info and "resources" in arch_info:
                 archive_paths = [r.get("archive_path") for r in arch_info["resources"]]
        
        if not archive_paths:
            return ""
            
        master_hasher = hashlib.sha256()
        valid_count = 0
        for path_str in sorted(archive_paths):
            p = Path(path_str)
            if p.exists():
                valid_count += 1
                if p.is_file():
                    master_hasher.update(HashCompute.file_hash(p).encode())
                elif p.is_dir():
                    master_hasher.update(HashCompute.directory_hash(p).encode())
            else:
                master_hasher.update(f"missing_archive:{path_str}".encode())
        
        return master_hasher.hexdigest() if valid_count > 0 else ""

# =============================================================================
#  Sandbox & Execution
# =============================================================================

class RuntimeSandbox:
    """Creates a temporary workspace by copying environment resources."""
    def __init__(self, resource_paths: List[str]):
        # Uniquify and resolve paths
        self.original_paths = []
        seen = set()
        for p in resource_paths:
            if p and p not in seen:
                self.original_paths.append(Path(p).resolve())
                seen.add(p)
        
        self.temp_dir = None
        self.sandboxed_resources = []

    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="agent_eval_")
        for src in self.original_paths:
            if src.exists():
                dst = Path(self.temp_dir) / src.name
                try:
                    if src.is_dir():
                        if dst.exists(): shutil.rmtree(dst)
                        shutil.copytree(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    self.sandboxed_resources.append({"path": str(dst), "label": src.name})
                except Exception as e:
                    print(f"Warning: Failed to copy {src} to sandbox: {e}")
        return self.sandboxed_resources, self.temp_dir

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except: pass


def _resolve_existing_path(path_str: Optional[str]) -> Optional[Path]:
    if not path_str:
        return None
    candidate = Path(path_str).expanduser()
    if candidate.exists():
        return candidate.resolve()

    repo_candidate = Path.cwd() / candidate
    if repo_candidate.exists():
        return repo_candidate.resolve()
    return None


def _normalize_prompt_environment_input(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        text = str(value).strip()
        return [text] if text else []
    if isinstance(value, list):
        normalized: List[str] = []
        for item in value:
            normalized.extend(_normalize_prompt_environment_input(item))
        return normalized
    return []


def _collect_environment_paths_for_prompt(
    task_def: Dict[str, Any],
    log_item: Dict[str, Any],
    explicit_paths: Optional[List[str]] = None,
) -> List[Path]:
    collected: List[Path] = []
    seen: set[str] = set()

    for raw_path in explicit_paths or []:
        resolved = _resolve_existing_path(raw_path)
        if resolved and str(resolved) not in seen:
            collected.append(resolved)
            seen.add(str(resolved))

    env_archive = log_item.get("environment_archive", {}) or {}
    task_info = log_item.get("task", {}) or {}
    explicit_candidates = []
    for container in (log_item, task_info, task_def):
        explicit_candidates.extend(
            _normalize_prompt_environment_input(container.get("prompt_environment"))
        )
        explicit_candidates.extend(
            _normalize_prompt_environment_input(container.get("prompt_environment_path"))
        )
        explicit_candidates.extend(
            _normalize_prompt_environment_input(container.get("prompt_environment_paths"))
        )

    for raw_path in explicit_candidates:
        resolved = _resolve_existing_path(raw_path)
        if resolved and str(resolved) not in seen:
            collected.append(resolved)
            seen.add(str(resolved))

    for resource in env_archive.get("resources", []) or []:
        for key in ("archive_path", "source_path", "path"):
            resolved = _resolve_existing_path(resource.get(key))
            if resolved and str(resolved) not in seen:
                collected.append(resolved)
                seen.add(str(resolved))

    for container in (log_item, task_info, task_def):
        for raw_path in container.get("environment_paths", []) or []:
            resolved = _resolve_existing_path(raw_path)
            if resolved and str(resolved) not in seen:
                collected.append(resolved)
                seen.add(str(resolved))

    return collected


def _render_environment_path(path: Path) -> str:
    if path.is_file():
        files = [path] if path.suffix == ".py" else []
    else:
        files = sorted(
            file_path for file_path in path.rglob("*.py")
            if file_path.is_file()
        )

    if not files:
        if path.is_dir():
            return f"[Environment directory: {path}]\nNo Python files found."
        return f"[Environment file: {path}]\nUnsupported file type for prompt injection."

    sections: List[str] = [f"[Environment root: {path}]"]
    for file_path in files:
        try:
            relative_name = str(file_path.relative_to(path)) if path.is_dir() else file_path.name
        except ValueError:
            relative_name = file_path.name

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            content = f"<<failed to read file: {exc}>>"

        sections.append(
            f"### File: {relative_name}\n```python\n{content.rstrip()}\n```"
        )
    return "\n\n".join(sections)


def build_environment_prompt_context(
    task_def: Dict[str, Any],
    log_item: Dict[str, Any],
    explicit_paths: Optional[List[str]] = None,
    max_chars: int = MAX_ENVIRONMENT_PROMPT_CHARS,
) -> str:
    rendered_blocks = []
    for path in _collect_environment_paths_for_prompt(task_def, log_item, explicit_paths=explicit_paths):
        rendered = _render_environment_path(path)
        if rendered:
            rendered_blocks.append(rendered)

    if not rendered_blocks:
        return "No environment Python files were found."

    combined = "\n\n".join(rendered_blocks)
    if len(combined) <= max_chars:
        return combined

    truncated = combined[:max_chars].rsplit("\n", 1)[0].rstrip()
    return f"{truncated}\n\n[Truncated: environment content exceeded prompt budget.]"

class EnvironmentExecutor:
    def __init__(self, tool_map: Dict[str, Any]):
        self.tool_map = tool_map
        self.exec_globals = self._prepare_globals()

    def _prepare_globals(self) -> Dict[str, Any]:
        import math, re, json, random, datetime, sqlite3, os, traceback
        import pandas as pd
        g = {
            "math": math, "re": re, "json": json, "random": random, 
            "datetime": datetime, "pd": pd, "pandas": pd, 
            "sqlite3": sqlite3, "os": os, "traceback": traceback
        }
        for name, tool in self.tool_map.items():
            g[name] = tool
            if hasattr(tool, 'name') and tool.name:
                g[tool.name] = tool
        return g

    def execute(self, actions: List[Any], env_resources: List[Dict[str, Any]], work_dir: str) -> Tuple[bool, Any, str]:
        # Hash initial state if no actions
        if not actions:
             if work_dir and os.path.exists(work_dir):
                 return True, HashCompute.compute_file_hashes_from_dir(Path(work_dir)), ""
             return True, {}, ""

        original_cwd = os.getcwd()
        try:
            # Switch to sandbox directory so code like sqlite3.connect('x.db') works
            if work_dir and os.path.exists(work_dir):
                os.chdir(work_dir)
                
            for action in actions:
                code = None
                if isinstance(action, str):
                    code = self._clean_code(action)
                elif isinstance(action, dict):
                    # Handle structured action dict (e.g. from Tau2Bench tasks)
                    func_name = action.get("name")
                    args = action.get("arguments", {})
                    if func_name:
                        # Ensure args is a dict
                        if isinstance(args, str):
                            try: args = json.loads(args)
                            except: pass
                        
                        if isinstance(args, dict):
                            # Construct kwargs string
                            args_str = ", ".join([f"{k}={repr(v)}" for k, v in args.items()])
                            code = f"{func_name}({args_str})"
                        else:
                            # Fallback or invalid args
                            continue

                if not code: continue
                exec(code, self.exec_globals)
            
            final_hashes = HashCompute.compute_file_hashes_from_dir(Path(work_dir))
            return True, final_hashes, ""
        except Exception as e:
            # traceback.print_exc()
            return False, {}, f"{type(e).__name__}: {str(e)}"
        finally:
            if os.getcwd() != original_cwd:
                os.chdir(original_cwd)

    @staticmethod
    def _clean_code(text: str) -> str:
        text = text.strip()
        if text.startswith("```python"): text = text[9:]
        elif text.startswith("```"): text = text[3:]
        if text.endswith("```"): text = text[:-3]
        return text.strip()

# =============================================================================
#  LLM Judge
# =============================================================================

class LLMJudge:
    # Default retry configuration; overridden by Evaluation.server.retry in YAML
    DEFAULT_RETRY = {
        "max_judge_retries": 5,
        "judge_base_delay": 2.0,
        "max_api_retries": 3,
        "api_base_delay": 1.0,
        "api_timeout": 600,
        "raise_on_exhausted": True,
    }

    def __init__(self, config: Dict[str, Any]):
        self.enabled = False
        self.eval_config = config
        self.server_config = config.get("server", {})
        if self.server_config and self.server_config.get("api_base"):
            self.enabled = True

        self.api_base = self.server_config.get("api_base")
        self.api_key = self.server_config.get("api_key", "EMPTY")
        self.model = self.server_config.get("model_id", "gpt-3.5-turbo")

        # Retry / timeout config: read from YAML (server.retry.*) with sane defaults
        retry_cfg = self.server_config.get("retry", {}) or {}
        merged = {**self.DEFAULT_RETRY, **retry_cfg}
        self.max_judge_retries = int(merged["max_judge_retries"])
        self.judge_base_delay = float(merged["judge_base_delay"])
        self.max_api_retries = int(merged["max_api_retries"])
        self.api_base_delay = float(merged["api_base_delay"])
        self.api_timeout = int(merged["api_timeout"])
        self.raise_on_exhausted = bool(merged["raise_on_exhausted"])

        self.system_prompt = self.server_config.get("system", "You are a helpful assistant.")
        self.user_template = self.server_config.get("evaluate", "")
        if openai and self.api_key :
            try:
                self.client = openai.OpenAI(
                    api_key=self.api_key,
                    base_url=self.api_base if self.api_base else None
                )
            except Exception as e:
                print(f"Warning: Failed to initialize OpenAI client: {e}")

        self.judge_prompt_template = self.server_config.get("judge_prompt_template",None)
        #如果有template模版路径，则应该加载template模版使用
        if self.judge_prompt_template:
            with open(self.judge_prompt_template, "r", encoding="utf-8") as f:
                template_data = yaml.safe_load(f)
            self.system_prompt = template_data.get("system", "You are a helpful assistant.")
            self.user_template = template_data.get("evaluate", "")


    def evaluate(self, task_def: Dict[str, Any], log_item: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled or not self.user_template:
            return {"error": "LLM Judge not configured"}

        # Extract context variables
        task_info = log_item.get("task")
        instruction = task_info.get("instruction") or task_info.get("name")
        label = task_info.get("label")
        
        # Final Memory
        final_mem = {}
        if "final_memory" in log_item:
            final_mem = log_item["final_memory"]
        elif "agent_state" in log_item: # fallback
            final_mem = log_item.get("agent_state", {})
        
        # Result (direct field)
        result_val = log_item.get("result", "")
        #如果为空，则导入error字段，并作为result字段
        if result_val == "" and "error" in log_item:
            result_val = log_item.get("error", "")
        explicit_paths = []
        explicit_paths.extend(
            _normalize_prompt_environment_input(self.eval_config.get("prompt_environment"))
        )
        explicit_paths.extend(
            _normalize_prompt_environment_input(self.eval_config.get("prompt_environment_path"))
        )
        explicit_paths.extend(
            _normalize_prompt_environment_input(self.server_config.get("prompt_environment"))
        )
        explicit_paths.extend(
            _normalize_prompt_environment_input(self.server_config.get("prompt_environment_path"))
        )
        environment_context = build_environment_prompt_context(
            task_def,
            log_item,
            explicit_paths=explicit_paths,
        )
        # Format Template
        try:
            user_content = self.user_template.format(
                instruction=instruction,
                label=label,
                environment=environment_context,
                final_memory=json.dumps(final_mem, indent=2, ensure_ascii=False),
                result=json.dumps(result_val, indent=2, ensure_ascii=False),
                log=json.dumps(final_mem, indent=2, ensure_ascii=False) # fallback if needed
            )
        except KeyError as e:
            # Handle missing placeholders gracefully
            user_content = f"Template Error: Missing key {e}\n\n" + self.user_template

        # Call API + parse with retries (config-driven)
        max_judge_retries = self.max_judge_retries
        base_delay = self.judge_base_delay

        llm_output = {
            "llm_score": None,
            "llm_reasoning": "",
            "llm_explanation": "",
            "llm_raw_response": None,
            "llm_prompt": f"System: {self.system_prompt}\nUser: {user_content}",
        }

        last_error = None
        last_resp = None
        for attempt in range(max_judge_retries):
            resp_data = self._call_api(user_content)
            last_resp = resp_data

            if not resp_data:
                last_error = "Empty response from LLM API"
            else:
                try:
                    clean_json = resp_data.strip()
                    if clean_json.startswith("```json"):
                        clean_json = clean_json[7:]
                    elif clean_json.startswith("```"):
                        clean_json = clean_json[3:]
                    if clean_json.endswith("```"):
                        clean_json = clean_json[:-3]

                    parsed = json.loads(clean_json.strip())
                    if isinstance(parsed, dict) and "score" in parsed:
                        llm_output["llm_score"] = float(parsed["score"])
                        llm_output["llm_reasoning"] = parsed.get("reasoning", "")
                        llm_output["llm_explanation"] = parsed.get("explanation", "")
                        llm_output["llm_raw_response"] = resp_data
                        if attempt > 0:
                            print(f"[LLMJudge] succeeded on retry {attempt + 1}/{max_judge_retries}")
                        return llm_output
                    last_error = "Parsed JSON missing 'score' key"
                except Exception as e:
                    last_error = f"JSON Parse Error: {e}"

            if attempt < max_judge_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(
                    f"[LLMJudge] attempt {attempt + 1}/{max_judge_retries} failed "
                    f"({last_error}); retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

        # All retries exhausted
        llm_output["llm_raw_response"] = last_resp
        llm_output["llm_error"] = last_error
        msg = (
            f"[LLMJudge] llm_score is None after {max_judge_retries} retries. "
            f"error={last_error!r}, raw_response={last_resp!r}"
        )
        if self.raise_on_exhausted:
            raise RuntimeError(msg)
        print(msg)
        return llm_output

    def _call_api(self, user_content: str) -> str:
        max_retries = self.max_api_retries
        base_delay = self.api_base_delay

        for attempt in range(max_retries):
            try:
                if self.client:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_content}
                        ],
                        temperature=0.0,
                        timeout=self.api_timeout,
                    )
                    content = response.choices[0].message.content
                else:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}"
                    }
                    payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self.system_prompt},
                            {"role": "user", "content": user_content}
                        ],
                        "temperature": 0.0,
                    }
                    resp = requests.post(
                        f"{self.api_base}/chat/completions",
                        headers=headers, json=payload, timeout=self.api_timeout,
                    )
                    resp.raise_for_status()
                    content = resp.json()["choices"][0]["message"]["content"]

                if content and content.strip():
                    return content
                # Empty content is treated as failure -> retry
                print(f"[_call_api] attempt {attempt + 1}/{max_retries}: empty content")
            except Exception as e:
                print(f"[_call_api] attempt {attempt + 1}/{max_retries} failed: {e}")

            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))

        return None

# =============================================================================
#  Evaluation Core Path Logic
# =============================================================================

def extract_timestamp_from_filename(filename: str) -> str:
    """
    Extracts a timestamp (YYYYMMDD_HHMMSS or similar) from a filename for sorting.
    Returns '0' if no timestamp found, to appear last in ascending or first in descending sort if used carefully.
    """
    import re
    # Match patterns like YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS
    # Look for 8 digits + separator + 6 digits
    match = re.search(r"(\d{8})[_-](\d{6})", filename)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    
    # Fallback: YYYYMMDD only?
    match_date = re.search(r"(\d{8})", filename)
    if match_date:
        return f"{match_date.group(1)}000000"
        
    return "0"

def find_environment_archive(base_dir: Path, task_id: str, timestamp_hint: str = None, model_hint: str = None) -> Optional[str]:
    """
    Finds module directory inside base_dir matching task_id, timestamp, and model.
    Pattern: *task_{task_id}*
    """
    if not base_dir.exists():
        return None
    
    # Search for all folders containing task_{id}
    # Note: Using glob to match wildcard
    search_pattern = f"*task_{task_id}*"
    candidates = list(base_dir.glob(search_pattern))
    candidates = [c for c in candidates if c.is_dir()]
    
    if not candidates:
        search_pattern_alt = f"*task{task_id}*" # Try without underscore just in case
        candidates = list(base_dir.glob(search_pattern_alt))
        candidates = [c for c in candidates if c.is_dir()]

    if not candidates:
        return None

    # Filter by model name if provided
    if model_hint:
        candidates = [c for c in candidates if model_hint in c.name]
        if not candidates:
            return None

    # Filter by timestamp if provided
    # If timestamp hint matches a directory name exactly (substring), prioritize it
    if timestamp_hint:
        precise_matches = [c for c in candidates if timestamp_hint in c.name]
        if precise_matches:
            # Sort by name length or other criteria? Just take last (latest lexicographically generally means latest time)
            precise_matches.sort(key=lambda x: x.name)
            return str(precise_matches[-1])

    if not candidates:
        return None

    # Fallback: Sort by modification time, newest first
    candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(candidates[0])

def get_source_paths(task_def: Dict[str, Any], log_item: Dict[str, Any], global_env_config: Dict[str, Any]) -> List[str]:
    """Robustly determine source environment paths."""
    candidates = []
    
    # Priority: Log > Task > Global Config
    if "environment_paths" in log_item:
        candidates.extend(log_item["environment_paths"])
    elif "task" in log_item and "environment_paths" in log_item["task"]:
        candidates.extend(log_item["task"]["environment_paths"])
    
    if not candidates and "environment_paths" in task_def:
        candidates.extend(task_def["environment_paths"])
        
    resolved = []
    repo_root = global_env_config.get("repo_root", Path.cwd())
    
    for p in candidates:
        if not p: continue
        path_obj = Path(p)
        
        # Check 1: Absolute Path
        if path_obj.is_absolute() and path_obj.exists():
            resolved.append(str(path_obj))
            continue
            
        # Check 2: Relative to Repo Root
        cand_root = repo_root / path_obj
        if cand_root.exists():
            resolved.append(str(cand_root))
            continue
            
        # Check 3: Relative to CWD
        cand_cwd = Path.cwd() / path_obj
        if cand_cwd.exists():
            resolved.append(str(cand_cwd))
            continue
            
        # Check 4: Inside 'Environment' folder (Common structure fix)
        # e.g. path is "Tau2Bench/..." but on disk it is "Environment/Tau2Bench/..."
        if not str(path_obj).startswith("Environment"):
            cand_env = repo_root / "Environment" / path_obj
            if cand_env.exists():
                resolved.append(str(cand_env))
                continue
    
    # Check 5: If nothing found yet, check Global Config Base Path
    if not resolved and global_env_config.get("base_path"):
         base = Path(global_env_config["base_path"])
         if base.exists():
             resolved.append(str(base))
             
    return resolved

def evaluate_single_task(
    task_def: Dict[str, Any],
    log_item: Dict[str, Any],
    executor: EnvironmentExecutor,
    env_config: Dict[str, Any],
    eval_config: Dict[str, Any],
    judge: Optional[LLMJudge] = None,
    run_timestamp: str = None,
    model_name: str = None,
    log_file_path: str = None,
    benchmark_path: str = ""
) -> Dict[str, Any]:
    
    # clean_log = extract_memory_fields(log_item)
    task_id = log_item.get("outer_task_id") or task_def.get("task_id") or "0"
    
    # Extract Step Counts
    total_step = log_item.get("total_step_count")
    per_agent_step = log_item.get("per_agent_step_counts", {})
    
    result = {
        "task_id": task_id,
        "log_path": log_file_path,
        "source_env_path": [],
        "archive_env_path": [],
        "score": 0.0, # default action score
        "hash_match": False,
        # "gold_hash": "", # Removed as primary metric per request
        # "actual_hash": "", 
        "gold_file_hashes": {},
        "actual_file_hashes": {},
        "file_details": {}, # Detailed breakdown of which files matched/failed
        "total_step_count": total_step,
        "per_agent_step_counts": per_agent_step,
        "total_input_tokens": log_item.get("total_input_tokens"),
        "total_output_tokens": log_item.get("total_output_tokens"),
        "total_tokens": log_item.get("total_tokens"),
        "elapsed_seconds": log_item.get("elapsed_seconds"),
        "error": ""
    }

    eval_type = eval_config.get("type", "actions")
    # Supports: "actions", "llm", "both"

    # Define flags based on Value content (non-empty check)
    actions_val = task_def.get("actions")
    has_actions = (actions_val is not None) and (len(actions_val) > 0)
    
    label_val = task_def.get("label")
    has_label = (label_val is not None) and (str(label_val).strip() != "")

    run_env = False
    run_llm = False

    if eval_type == "actions":
        run_env = True
    elif eval_type == "llm":
        run_llm = True
    elif eval_type in ["both", "all"]:
        if has_actions and has_label:
            run_env = True
            run_llm = True
        elif has_actions:
            run_env = True
        elif has_label:
            run_llm = True

    action_score = 0.0
    llm_score = 0.0

    # --- 1. Action/State Matching Evaluation ---
    if run_env:
        # New resource extraction logic
        env_arch = log_item.get("environment_archive", {})
        resources = env_arch.get("resources", [])
        
        source_paths = []
        archive_map = {} # label -> absolute_path_to_archive_file
        label_to_filename = {} # label -> expected_filename_in_sandbox

        for r in resources:
            s_p = r.get("source_path")
            a_p = r.get("archive_path")
            lbl = r.get("label")
            
            if s_p:
                source_paths.append(s_p)
                if lbl:
                    # In sandbox, file is copied with its original name
                    label_to_filename[lbl] = os.path.basename(s_p)
            
            if lbl and a_p:
                # Directly use archive_path, try multiple path corrections
                final_ap = None
                candidates_to_try = [
                    a_p,  # Original path as-is
                    f"/{a_p[9:]}" if a_p.startswith("resource/") else None,  # /mnt/... form
                    a_p[9:] if a_p.startswith("resource/") else None,  # mnt/... form (relative)
                ]
                
                for cand in candidates_to_try:
                    if cand and os.path.exists(cand):
                        final_ap = cand
                        break
                
                # If still not found, use original anyway for error reporting
                if not final_ap:
                    final_ap = a_p
                
                archive_map[lbl] = final_ap

        result["source_env_path"] = source_paths
        result["archive_env_path"] = list(archive_map.values())
        
        if not source_paths and not resources:
             result["error"] = "No resources found in log environment_archive"
        
        # Calculate Actual Hash: DIRECTLY read archive file and compute hash
        actual_hashes = {}
        for lbl, path_str in archive_map.items():
            p = Path(path_str)
            if p.exists() and p.is_file():
                actual_hashes[lbl] = HashCompute.compute_content_hash(p)
            else:
                actual_hashes[lbl] = f"file_not_found:{path_str}"

        result["actual_file_hashes"] = actual_hashes

        # Execute Gold Actions and Calculate Gold Hash
        gold_hashes_filtered = {}
        if source_paths:
            gold_actions = task_def.get("actions", [])
            # Execute Gold Actions
            try:
                with RuntimeSandbox(source_paths) as (sandboxed_resources, temp_dir):
                    if not sandboxed_resources:
                        result["error"] = f"Failed to load resources from: {source_paths}"
                    else:
                        exec_dir = temp_dir # Execute in the sandbox root
                        
                        # Tau/Tau2 specific: Initialize environment for in-memory modification
                        is_tau_bench = False
                        if benchmark_path and ("TauBench" in benchmark_path or "Tau2Bench" in benchmark_path):
                            is_tau_bench = True
                            set_task_environment_resources(sandboxed_resources)

                        # Execute actions (ignore returned hashes, we calculate manually)
                        success, _, error = executor.execute(gold_actions, sandboxed_resources, exec_dir)
                        if not success:
                            result["error"] = f"Gold Execution Failed: {error}"
                        
                        # Tau/Tau2 specific: Flush in-memory changes to sandbox disk for hash calculation
                        if is_tau_bench:
                            updated_resources = get_task_environment_resources()
                            for res in updated_resources:
                                data = res.get("data")
                                path_str = res.get("path")
                                if data is not None and path_str:
                                    # Ensure we are modifying the sandbox file
                                    p = Path(path_str)
                                    # Check if path is within temp_dir to avoid modifying external files
                                    if str(temp_dir) in str(p.resolve()) and p.is_file():
                                        try:
                                            # Using indent=2 to match typical JSON dump format in archive
                                            with open(p, "w", encoding="utf-8") as f:
                                                if isinstance(data, (dict, list)):
                                                    json.dump(data, f, indent=2, ensure_ascii=False)
                                                else:
                                                    f.write(str(data))
                                        except Exception as e:
                                            print(f"Warning: Failed to flush resource {res.get('label')} to disk: {e}")

                        # Calculate Gold Hash: DIRECTLY read sandbox file and compute hash
                        # Use same method as actual_hashes for consistency
                        if label_to_filename:
                            for lbl, fname in label_to_filename.items():
                                sandbox_file = Path(temp_dir) / fname
                                if sandbox_file.exists() and sandbox_file.is_file():
                                    gold_hashes_filtered[lbl] = HashCompute.compute_content_hash(sandbox_file)
                                else:
                                    gold_hashes_filtered[lbl] = f"file_not_found_in_sandbox:{sandbox_file}"
                        else:
                            # Fallback: hash all files
                            full_map = HashCompute.compute_file_hashes_from_dir(Path(temp_dir))
                            gold_hashes_filtered = full_map

            except Exception as e:
                result["error"] = f"Sandbox Exception: {e}"
        
        result["gold_file_hashes"] = gold_hashes_filtered
            
        # --- Strict File-by-File Comparison ---
        if result.get("gold_file_hashes"):
            match_count = 0
            # Compare based on keys in gold hashes
            total_files = len(result["gold_file_hashes"])
            file_status = {}
            
            for lbl, g_val in result["gold_file_hashes"].items():
                a_val = result["actual_file_hashes"].get(lbl, "missing_comparison")
                is_match = (g_val == a_val)
                file_status[lbl] = "match" if is_match else "mismatch"
                if is_match:
                    match_count += 1
            
            result["file_details"] = file_status
            result["hash_match"] = (match_count == total_files) and (total_files > 0)
            
            if result["hash_match"]:
                 action_score = 1.0

    # --- 2. LLM Judge Evaluation ---
    if run_llm and judge:
        llm_res = judge.evaluate(task_def, log_item)
        result.update(llm_res)
        llm_score = result.get("llm_score", 0.0)
    
    # --- Final Score Logic ---
    if eval_type == "actions":
        result["score"] = action_score
    elif eval_type == "llm":
        result["score"] = llm_score
    elif eval_type in ["both", "all"]:
        if has_actions and has_label:
            result["score"] = action_score * llm_score
        elif has_actions:
            result["score"] = action_score
        elif has_label:
            result["score"] = llm_score
        else:
            result["score"] = 0.0

    # Legacy field alignment
    result["match"] = result.get("hash_match", False)

    return result

# =============================================================================
#  Main CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="eval_config.yaml")
    parser.add_argument("--logs", required=False)
    parser.add_argument("--output", required=False)
    parser.add_argument("--timestamp", required=False, help="Specific timestamp identifier")
    parser.add_argument("--model", required=False, help="Specific model identifier")
    parser.add_argument(
        "--prompt-environment",
        required=False,
        action="append",
        help="Explicit path for filling the {environment} prompt variable. Can be passed multiple times.",
    )
    args = parser.parse_args()

    # Setup
    config = read_config(args.config)
    env_config = normalize_environment_config(config, Path(".").resolve())
    eval_config = config.get("Evaluation", {}) # Create eval config dict
    if args.prompt_environment:
        eval_config["prompt_environment_path"] = args.prompt_environment
    
    # Retrieve environment_archive_dir from config root or Result section
    if "environment_archive_dir" not in env_config and "Result" in config:
         raw_arch = config["Result"].get("environment_archive_dir")
         if raw_arch:
             env_config["environment_archive_dir"] = str(Path(raw_arch).resolve())

    set_global_environment_context(env_config)
    
    print("Loading Tools...")
    tools = load_tools(config)
    executor = EnvironmentExecutor({t.name: t for t in tools})
    
    # Initialize LLM Judge if needed
    judge = None
    if eval_config.get("type") in ["llm", "both", "all"]:
        print("Initializing LLM Judge...")
        judge = LLMJudge(eval_config)

    print("Loading Benchmarks...")
    tasks = load_benchmark_tasks(config)
    benchmark_path = config.get("Benchmark", {}).get("path", "")
    
    # Robust Task Mapping
    task_map = {}
    for idx, t in enumerate(tasks):
        raw_id = t.get("task_id") or t.get("id")
        if raw_id is not None:
             task_map[str(raw_id)] = t
        
        seq_id = str(idx + 1)
        if seq_id not in task_map: task_map[seq_id] = t
        if f"task_{seq_id}" not in task_map: task_map[f"task_{seq_id}"] = t

    # Resolve Logs (Config Priority)
    
    # Pre-calculate filters: args > config['Result']
    res_cfg_temp = config.get("Result", {})
    
    filter_timestamp = args.timestamp
    if not filter_timestamp:
        filter_timestamp = res_cfg_temp.get("run_timestamp")
    if filter_timestamp: filter_timestamp = str(filter_timestamp)

    filter_model = args.model
    if not filter_model:
        filter_model = res_cfg_temp.get("model_tag")
    if filter_model: filter_model = str(filter_model)

    log_path = None
    if args.logs:
        log_path = Path(args.logs)
    else:
        # Check Result.log_dir from config
        res_cfg = config.get("Result", {})
        
        # Search in both log_dir and save_dir
        raw_search_paths = []
        if res_cfg.get("log_dir"): 
            raw_search_paths.append(str(res_cfg["log_dir"]))
        if res_cfg.get("save_dir"):
            raw_search_paths.append(str(res_cfg["save_dir"]))

        search_dirs = []
        
        # Setup resolution bases: [CWD, ScriptDir, ConfigDir]
        resolution_bases = [Path.cwd()]
        script_dir = Path(__file__).resolve().parent
        if script_dir != Path.cwd():
             resolution_bases.append(script_dir)
        
        if args.config:
             config_path = Path(args.config).resolve()
             resolution_bases.append(config_path.parent)

        seen_dirs = set()

        for raw in raw_search_paths:
             # Try absolute
             p = Path(raw)
             if p.is_absolute():
                 if p.exists() and str(p) not in seen_dirs:
                     search_dirs.append(p)
                     seen_dirs.add(str(p))
                 continue
             
             # Try relative to bases
             found = False
             for base in resolution_bases:
                 cand = base / p
                 if cand.exists():
                     if str(cand) not in seen_dirs:
                         search_dirs.append(cand)
                         seen_dirs.add(str(cand))
                     found = True
                     break
             
             if not found:
                 print(f"Warning: Could not find log directory: {raw}")

        candidates = []
        for p in search_dirs:
            print(f"Scanning for logs in: {p}")
            if p.exists():
                candidates.extend(list(p.glob("*.jsonl")))

        # Filter to avoid reading eval outputs or intermediate files
        # We allow "result" now (e.g. gpt-4.1_results_...), but exclude "eval_results"
        candidates = [c for c in candidates if "eval_results" not in c.name.lower() and "clean" not in c.name.lower()]
        
        print(f"Found {len(candidates)} candidate logs before filtering.")

        # Apply timestamp filter if provided
        if filter_timestamp:
            print(f"Filtering by timestamp: {filter_timestamp}")
            
            def match_ts(fname, ts_filter):
                if ts_filter in fname: 
                    return True
                # Handle PyYAML integer parsing side-effect (e.g. 20260124_123350 -> 20260124123350)
                # If filter is 14 digits, try matching YYYYMMDD_HHMMSS
                if len(ts_filter) == 14 and ts_filter.isdigit():
                    reconstructed = f"{ts_filter[:8]}_{ts_filter[8:]}"
                    if reconstructed in fname:
                        return True
                return False

            candidates = [c for c in candidates if match_ts(c.name, filter_timestamp)]
        
        # Apply model filter if provided
        if filter_model:
            print(f"Filtering by model: {filter_model}")
            candidates = [c for c in candidates if filter_model in c.name]

        if candidates:
            # Sort first by parsed filename timestamp (descending), then by mtime as fallback
            candidates.sort(
                key=lambda x: (extract_timestamp_from_filename(x.name), x.stat().st_mtime), 
                reverse=True
            )
            log_path = candidates[0]
            print(f"Auto-detected log: {log_path}")
    
    if not log_path or not log_path.exists():
        print("Error: No logs found/resolved.")
        # Debug info
        if not args.logs:
             print(f"Search directories: {[str(d) for d in search_dirs]}")
             print(f"Filters -> Model: {filter_model}, Timestamp: {filter_timestamp}")
        return

    # Extract metadata/identifiers from log filename or args
    # Format attempt: {model}_logs_{timestamp}_{others}.jsonl
    run_timestamp_hint = filter_timestamp
    model_hint = filter_model
    
    # Try reading from Config if not in args (Redundant check kept for safety if logic flow changes)
    res_conf = config.get("Result", {})
    if not run_timestamp_hint:
         run_timestamp_hint = res_conf.get("run_timestamp")
    if not model_hint:
         model_hint = res_conf.get("model_tag")

    # Ensure metadata are strings (handle YAML parsing numbers)
    if run_timestamp_hint is not None:
        run_timestamp_hint = str(run_timestamp_hint)
    if model_hint is not None:
        model_hint = str(model_hint)

    # Try inferring from filename
    if log_path:
        stem = log_path.stem
        # Common convention: model_logs_timestamp... or model_results_timestamp...
        delimiter = None
        if "_logs_" in stem:
            delimiter = "_logs_"
        elif "_results_" in stem:
            delimiter = "_results_"

        if delimiter:
            parts = stem.split(delimiter)
            if not model_hint and len(parts) > 0:
                model_hint = parts[0]
            
            if not run_timestamp_hint and len(parts) > 1:
                # usually follows delimiter
                remaining = parts[1] # e.g. 20260119_205655_multi...
                # YYYYMMDD_HHMMSS is 15 chars
                if len(remaining) >= 15 and remaining[8] == '_':
                    potential_ts = remaining[:15]
                    # Check if all digit where expected
                    if potential_ts.replace('_', '').isdigit():
                        run_timestamp_hint = potential_ts

    print(f"Run Context -> Model: {model_hint}, Timestamp: {run_timestamp_hint}")

    # Process
    results = []
    print(f"Processing {log_path}...")
    with open(log_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip(): continue
            try:
                log_item = json.loads(line)
                
                # Priority 1: Check internal 'task' object for original ID (TauBench style logs)
                inner_task = log_item.get("task", {})
                inner_tid = str(inner_task.get("task_id") or inner_task.get("id") or "")
                
                root_tid = str(log_item.get("task_id") or log_item.get("outer_task_id") or "")
                
                task_def = None
                
                # Try looking up with inner ID first
                if inner_tid:
                     task_def = task_map.get(inner_tid)
                
                # Fallback to root ID if inner ID lookup failed or wasn't present
                if not task_def and root_tid:
                     task_def = task_map.get(root_tid)
                     if not task_def and root_tid.startswith("task_"):
                         task_def = task_map.get(root_tid.replace("task_", ""))

                # Fallback to sequence
                if not task_def:
                     seq_tid = str(i + 1)
                     task_def = task_map.get(seq_tid)

                tid = inner_tid if inner_tid else (root_tid if root_tid else str(i+1))
                
                if not task_def:
                    print(f"Skipping Task {tid} (Line {i+1}): Not found in map.")
                    continue
                
                print(f"Evaluating Task {tid}...", end="\r")
                res = evaluate_single_task(
                    task_def, 
                    log_item, 
                    executor, 
                    env_config,
                    eval_config,
                    judge=judge,
                    run_timestamp=run_timestamp_hint,
                    model_name=model_hint,
                    log_file_path=str(log_path),
                    benchmark_path=benchmark_path
                )
                results.append(res)
                
            except Exception as e:
                print(f"\nError Line {i+1}: {e}")
                traceback.print_exc()
                raise

    # Output (Config Priority)
    out_path = args.output
    if not out_path:
        eval_cfg = config.get("Evaluation", {})
        save_dir = eval_cfg.get("save_dir", ".")
        os.makedirs(save_dir, exist_ok=True)
        
        # Construct output name based on run context to match log/env
        out_ts = run_timestamp_hint if run_timestamp_hint else datetime.now().strftime('%Y%m%d_%H%M%S')
        out_model_prefix = f"{model_hint}_" if model_hint else ""
        out_name = f"eval_results_{out_model_prefix}{out_ts}.jsonl"
        
        out_path = os.path.join(save_dir, out_name)
        
    print(f"\nWriting results to {out_path}...")
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
            
    matches = sum(1 for r in results if r.get("match") or r.get("llm_score", 0) == 1.0)
    print(f"Total: {len(results)}, High Score/Match: {matches}, Ratio: {(matches/len(results)*100 if results else 0):.2f}%")

    # =============================================================================
    #  Generate Final Summary Report
    # =============================================================================
    if results:
        num_tasks = len(results)

        # Calculate averages (only count non-None values)
        valid_scores = [r.get("score") for r in results if r.get("score") is not None]
        avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

        valid_step_counts = [r.get("total_step_count") for r in results if r.get("total_step_count") is not None]
        avg_total_step_count = sum(valid_step_counts) / len(valid_step_counts) if valid_step_counts else 0

        valid_input_tokens = [r.get("total_input_tokens") for r in results if r.get("total_input_tokens") is not None]
        avg_total_input_tokens = sum(valid_input_tokens) / len(valid_input_tokens) if valid_input_tokens else 0

        valid_output_tokens = [r.get("total_output_tokens") for r in results if r.get("total_output_tokens") is not None]
        avg_total_output_tokens = sum(valid_output_tokens) / len(valid_output_tokens) if valid_output_tokens else 0

        valid_tokens = [r.get("total_tokens") for r in results if r.get("total_tokens") is not None]
        avg_total_tokens = sum(valid_tokens) / len(valid_tokens) if valid_tokens else 0

        valid_elapsed = [r.get("elapsed_seconds") for r in results if r.get("elapsed_seconds") is not None]
        avg_elapsed_seconds = sum(valid_elapsed) / len(valid_elapsed) if valid_elapsed else 0.0

        # Calculate totals (only sum non-None values)
        total_input_tokens_all = sum(valid_input_tokens) if valid_input_tokens else 0
        total_output_tokens_all = sum(valid_output_tokens) if valid_output_tokens else 0
        total_tokens_all = sum(valid_tokens) if valid_tokens else 0
        total_elapsed_seconds_all = sum(valid_elapsed) if valid_elapsed else 0.0

        # Aggregate per_agent_step_counts
        aggregated_per_agent_steps = {}
        for r in results:
            per_agent = r.get("per_agent_step_counts", {})
            if isinstance(per_agent, dict):
                for agent_name, steps in per_agent.items():
                    if agent_name not in aggregated_per_agent_steps:
                        aggregated_per_agent_steps[agent_name] = []
                    aggregated_per_agent_steps[agent_name].append(steps)

        avg_per_agent_step_counts = {
            agent: sum(steps_list) / len(steps_list)
            for agent, steps_list in aggregated_per_agent_steps.items()
        }

        # Build summary report
        summary_report = {
            "benchmark_name": config.get("Benchmark", {}).get("path", "Unknown"),
            "model": model_hint or "Unknown",
            "run_timestamp": run_timestamp_hint or datetime.now().strftime('%Y%m%d_%H%M%S'),
            "evaluation_timestamp": datetime.now().isoformat(),
            "log_file": str(log_path),
            "num_tasks": num_tasks,
            "num_matches": matches,
            "match_ratio": matches / num_tasks if num_tasks > 0 else 0.0,
            "averages": {
                "score": round(avg_score, 4),
                "total_step_count": round(avg_total_step_count, 2),
                "per_agent_step_counts": {k: round(v, 2) for k, v in avg_per_agent_step_counts.items()},
                "total_input_tokens": round(avg_total_input_tokens, 2),
                "total_output_tokens": round(avg_total_output_tokens, 2),
                "total_tokens": round(avg_total_tokens, 2),
                "elapsed_seconds": round(avg_elapsed_seconds, 2),
            },
            "totals": {
                "total_input_tokens": total_input_tokens_all,
                "total_output_tokens": total_output_tokens_all,
                "total_tokens": total_tokens_all,
                "elapsed_seconds": round(total_elapsed_seconds_all, 2),
            }
        }

        # Save summary report
        summary_path = out_path.replace(".jsonl", "_summary.json")
        if not summary_path.endswith("_summary.json"):
            summary_path = out_path + "_summary.json"

        print(f"\nWriting summary report to {summary_path}...")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, indent=2, ensure_ascii=False)

        # Print summary to console
        print("\n" + "=" * 60)
        print("BENCHMARK EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Benchmark: {summary_report['benchmark_name']}")
        print(f"Model: {summary_report['model']}")
        print(f"Tasks Evaluated: {num_tasks}")
        print(f"Match/High Score: {matches} ({summary_report['match_ratio']*100:.2f}%)")
        print("-" * 60)
        print("AVERAGES (per task):")
        print(f"  Score:              {avg_score:.4f}")
        print(f"  Step Count:         {avg_total_step_count:.2f}")
        print(f"  Input Tokens:       {avg_total_input_tokens:.2f}")
        print(f"  Output Tokens:      {avg_total_output_tokens:.2f}")
        print(f"  Total Tokens:       {avg_total_tokens:.2f}")
        print(f"  Elapsed Time (s):   {avg_elapsed_seconds:.2f}")
        if avg_per_agent_step_counts:
            print("  Per-Agent Steps:")
            for agent, steps in avg_per_agent_step_counts.items():
                print(f"    - {agent}: {steps:.2f}")
        print("-" * 60)
        print("TOTALS (all tasks):")
        print(f"  Total Input Tokens:  {total_input_tokens_all}")
        print(f"  Total Output Tokens: {total_output_tokens_all}")
        print(f"  Total Tokens:        {total_tokens_all}")
        print(f"  Total Time (s):      {total_elapsed_seconds_all:.2f}")
        print("=" * 60)

if __name__ == "__main__":
    main()
