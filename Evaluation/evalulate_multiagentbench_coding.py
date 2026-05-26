#!/usr/bin/env python3
"""
Evaluation Script for MultiAgentBench Coding Tasks.
Uses Gemini 3 Flash for LLM-based evaluation with custom prompt templates.

Automatically scans results directory for task directories and evaluates them.
"""

import argparse
import json
import os
import re
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from openai import OpenAI


# =============================================================================
#  Configuration
# =============================================================================

def load_benchmark_tasks(benchmark_path: str) -> List[Dict[str, Any]]:
    """Load benchmark tasks from JSONL file."""
    tasks = []
    with open(benchmark_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                tasks.append(json.loads(line))
    return tasks


def load_evaluation_prompt(prompt_template_path: str) -> Dict[str, str]:
    """Load evaluation prompt template from YAML file."""
    with open(prompt_template_path, "r", encoding="utf-8") as f:
        template_data = yaml.safe_load(f)
    return {
        "system": template_data.get("system", ""),
        "evaluate": template_data.get("evaluate", "")
    }


# =============================================================================
#  Directory Scanning
# =============================================================================

def scan_result_directories(results_dir: str) -> Dict[int, str]:
    """
    Scan results directory and extract task_id -> directory path mapping.
    Looks for directories matching pattern: task_{task_id}__model_*
    Returns a dict: {task_id: directory_path}
    """
    base_path = Path(results_dir)
    if not base_path.exists():
        return {}
    
    task_dirs = {}
    
    for dir_path in base_path.iterdir():
        if not dir_path.is_dir():
            continue
        
        # Match pattern: task_{task_id}__model_*
        match = re.match(r'task_(\d+)__model_', dir_path.name)
        if match:
            task_id = int(match.group(1))
            task_dirs[task_id] = str(dir_path)
    
    return task_dirs


# =============================================================================
#  Environment Context Builder
# =============================================================================

def build_environment_context(solution_dir: str) -> str:
    """
    Read all Python files from the solution directory and combine them into 
    an environment context string.
    """
    solution_path = Path(solution_dir)
    if not solution_path.exists():
        return "No solution files found."
    
    # Find all Python files
    python_files = sorted(solution_path.rglob("*.py"))
    
    if not python_files:
        return "No Python files found in solution directory."
    
    sections = []
    for file_path in python_files:
        try:
            relative_name = str(file_path.relative_to(solution_path))
            content = file_path.read_text(encoding="utf-8")
            
            sections.append(
                f"### File: {relative_name}\n```python\n{content.rstrip()}\n```"
            )
        except Exception as e:
            sections.append(f"### File: {file_path.name}\n<<failed to read: {e}>>")
    
    return "\n\n".join(sections)


# =============================================================================
#  LLM Judge
# =============================================================================

class GeminiJudge:
    """LLM Judge using Google's Gemini API."""
    
    def __init__(
        self, 
        api_key: str, 
        api_base_url: str,
        model_name: str = "gemini-2.0-flash-exp",
        system_prompt: str = "",
        evaluate_template: str = ""
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.evaluate_template = evaluate_template
        
        self.client = OpenAI(api_key=api_key, base_url=api_base_url
        )
    
    def evaluate(
        self, 
        instruction: str, 
        environment: str
    ) -> Dict[str, Any]:
        """
        Evaluate a single task using the LLM.
        
        Args:
            instruction: The task instruction from benchmark
            environment: The solution code from result directory
            
        Returns:
            Dict with score, explanation, and raw response
        """
        if not self.client:
            return {
                "score": 0,
                "explanation": "LLM client not initialized",
                "error": "Missing API key or client"
            }
        
        # Format the evaluation prompt
        user_content = self.evaluate_template.format(
            instruction=instruction,
            environment=environment
        )
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0,
            )
            
            # Parse the response
            return self._parse_response(response.choices[0].message.content)
            
        except Exception as e:
            return {
                "score": 0,
                "explanation": f"API error: {str(e)}",
                "error": str(e)
            }
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON response from LLM."""
        # Clean markdown code blocks if present
        clean_json = response_text.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:]
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:]
        if clean_json.endswith("```"):
            clean_json = clean_json[:-3]
        
        try:
            parsed = json.loads(clean_json.strip())
            return {
                "score": float(parsed.get("score", 0)),
                "explanation": parsed.get("explanation", ""),
                "raw_response": response_text
            }
        except json.JSONDecodeError as e:
            return {
                "score": 0,
                "explanation": f"Failed to parse JSON: {e}",
                "raw_response": response_text
            }


# =============================================================================
#  Evaluation Logic
# =============================================================================

def run_evaluation(
    benchmark_path: str,
    results_dir: str,
    prompt_template_path: str,
    api_key: str,
    api_base_url: str,
    model_name: str,
    output_path: str,
    task_ids: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Run evaluation on all tasks found in results directory."""
    
    # First, load benchmark tasks for instruction lookup
    print(f"Loading benchmark tasks from {benchmark_path}...")
    benchmark_tasks = load_benchmark_tasks(benchmark_path)
    # instruction is a string directly, not a dict with "content" key
    task_instructions = {t.get("task_id"): t.get("instruction", "") for t in benchmark_tasks}
    print(f"Loaded {len(benchmark_tasks)} benchmark tasks")
    
    # Scan results directory to find available task directories
    print(f"Scanning results directory: {results_dir}...")
    available_tasks = scan_result_directories(results_dir)
    print(f"Found {len(available_tasks)} task directories: {sorted(available_tasks.keys())}")
    
    # Load evaluation prompt template
    print(f"Loading prompt template from {prompt_template_path}...")
    prompt_template = load_evaluation_prompt(prompt_template_path)
    print(f"System prompt length: {len(prompt_template['system'])} chars")
    print(f"Evaluate template length: {len(prompt_template['evaluate'])} chars")
    
    # Initialize judge
    judge = GeminiJudge(
        api_key=api_key,
        api_base_url=api_base_url,
        model_name=model_name,
        system_prompt=prompt_template["system"],
        evaluate_template=prompt_template["evaluate"]
    )
    
    # Filter by task_ids if specified, otherwise evaluate all found tasks
    if task_ids:
        task_ids_to_eval = {tid: available_tasks.get(tid) for tid in task_ids if tid in available_tasks}
        print(f"Evaluating {len(task_ids_to_eval)} specified tasks")
    else:
        task_ids_to_eval = available_tasks
    
    # Evaluate each task
    results = []
    for task_id, solution_dir in sorted(task_ids_to_eval.items()):
        print(f"Evaluating task {task_id}...", end="\r")
        
        # Get instruction from benchmark
        instruction = task_instructions.get(task_id, "")
        if not instruction:
            print(f"Warning: No instruction found for task {task_id}, skipping...")
            continue
        
        # Build environment context from solution files
        environment = build_environment_context(solution_dir)
        
        # Call judge
        result = judge.evaluate(instruction, environment)
        
        eval_result = {
            "task_id": task_id,
            "instruction_preview": instruction[:200] + "..." if len(instruction) > 200 else instruction,
            "solution_dir": solution_dir,
            "score": result.get("score", 0),
            "explanation": result.get("explanation", ""),
            "raw_response": result.get("raw_response", ""),
            "error": result.get("error", "")
        }
        results.append(eval_result)
        
        print(f"Task {task_id}: score={eval_result['score']}")
    
    print(f"\nEvaluated {len(results)} tasks")
    
    # Save results
    print(f"Writing results to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    # ==================== Calculate Statistics ====================
    scores = [r.get("score", 0) for r in results if r.get("score", 0) > 0]
    
    if not scores:
        print("\nNo valid scores to calculate statistics.")
        return results
    
    # Basic statistics
    total_tasks = len(results)
    valid_scores_count = len(scores)
    avg_score = sum(scores) / len(scores) if scores else 0
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 0
    
    # Calculate score distribution
    score_ranges = {
        "1.0-1.9": 0,
        "2.0-2.9": 0,
        "3.0-3.9": 0,
        "4.0-4.9": 0,
        "5.0": 0
    }
    for s in scores:
        if s < 2.0:
            score_ranges["1.0-1.9"] += 1
        elif s < 3.0:
            score_ranges["2.0-2.9"] += 1
        elif s < 4.0:
            score_ranges["3.0-3.9"] += 1
        elif s < 5.0:
            score_ranges["4.0-4.9"] += 1
        else:
            score_ranges["5.0"] += 1
    
    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total tasks evaluated: {total_tasks}")
    print(f"Tasks with valid scores: {valid_scores_count}")
    print("-" * 60)
    print("SCORE STATISTICS:")
    print(f"  Average Score: {avg_score:.4f}")
    print(f"  Min Score:    {min_score:.1f}")
    print(f"  Max Score:    {max_score:.1f}")
    print("-" * 60)
    print("SCORE DISTRIBUTION:")
    for range_name, count in score_ranges.items():
        pct = (count / valid_scores_count * 100) if valid_scores_count > 0 else 0
        print(f"  {range_name}: {count} ({pct:.1f}%)")
    print("=" * 60)
    
    # Save detailed summary
    summary = {
        "benchmark": benchmark_path,
        "results_dir": results_dir,
        "model": model_name,
        "timestamp": datetime.now().isoformat(),
        "statistics": {
            "total_tasks": total_tasks,
            "valid_scores": valid_scores_count,
            "average_score": round(avg_score, 4),
            "min_score": min_score,
            "max_score": max_score,
            "score_distribution": score_ranges
        },
        "individual_results": results
    }
    
    summary_path = output_path.replace(".jsonl", "_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nDetailed summary saved to: {summary_path}")
    
    return results


# =============================================================================
#  Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate MultiAgentBench coding tasks using Gemini")
    
    # API Configuration (user provides these)
    parser.add_argument("--api-key", default="your-api-key-here", help="Gemini API key")
    parser.add_argument("--api-url", default="http://your-api-server:port/v1", 
                        help="API base URL (optional)")
    parser.add_argument("--model", default="gemini-3-flash-preview",
                        help="Model name to use")
    
    # Paths
    parser.add_argument("--benchmark", 
                        default="Benchmark/MultiAgentBench/coding/coding_merged_clean.jsonl",
                        help="Path to benchmark tasks JSONL")
    parser.add_argument("--results-dir",
                        default="Results/tem_workspce/multiagentbench/coding_gemini_3",
                        help="Directory containing task results")
    parser.add_argument("--prompt-template",
                        default="Evaluation/prompt_templates/MAS_prompt_templates/evaluation_coding_prompts.yaml",
                        help="Path to evaluation prompt template YAML")
    parser.add_argument("--output",
                        default="Results/evaluations/MultiAgentBench/coding/eval_results_gemini_3.jsonl",
                        help="Output path for evaluation results")
    
    # Optional: filter specific task IDs
    parser.add_argument("--task-ids", nargs="*", type=int, 
                        help="Specific task IDs to evaluate (default: all)")
    
    args = parser.parse_args()
    
    # Make paths absolute if relative
    # Use current working directory as project root
    project_root = os.getcwd()
    
    benchmark_path = args.benchmark if os.path.isabs(args.benchmark) else os.path.join(project_root, args.benchmark)
    results_dir = args.results_dir if os.path.isabs(args.results_dir) else os.path.join(project_root, args.results_dir)
    prompt_template = args.prompt_template if os.path.isabs(args.prompt_template) else os.path.join(project_root, args.prompt_template)
    output_path = args.output if os.path.isabs(args.output) else os.path.join(project_root, args.output)
    
    print(f"Benchmark: {benchmark_path}")
    print(f"Results Dir: {results_dir}")
    print(f"Prompt Template: {prompt_template}")
    print(f"Output: {output_path}")
    print(f"Model: {args.model}")
    print()
    
    # Run evaluation
    run_evaluation(
        benchmark_path=benchmark_path,
        results_dir=results_dir,
        prompt_template_path=prompt_template,
        api_key=args.api_key,
        api_base_url=args.api_url,
        model_name=args.model,
        output_path=output_path,
        task_ids=args.task_ids
    )


if __name__ == "__main__":
    main()