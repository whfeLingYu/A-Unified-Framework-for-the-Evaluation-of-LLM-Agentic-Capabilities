# BFCL Prompt Template Mapping

This file maps each eval_data file to its corresponding prompt template.

## Template Mapping

| Eval Data File | Prompt Template |
    # Simple single-round
    "simple_python": "simple_single_round.yaml",
    "simple_java": "simple_single_round.yaml",
    "simple_javascript": "simple_single_round.yaml",
    "sql": "simple_single_round.yaml",
    "rest": "simple_single_round.yaml",
    "exec_simple": "simple_single_round.yaml",
    "live_simple": "simple_single_round.yaml",
    # Parallel calls
    "parallel": "parallel_calls.yaml",
    "parallel_multiple": "parallel_calls.yaml",
    "exec_parallel": "exec_parallel.yaml",  # Specialized template for exec_parallel
    "exec_parallel_multiple": "parallel_calls.yaml",
    "live_parallel": "live_parallel.yaml",
    "live_parallel_multiple": "live_parallel_multiple.yaml",
    # Multiple sequential
    "multiple": "multiple_sequential.yaml",
    "exec_multiple": "multiple_sequential.yaml",
    "live_multiple": "multiple_sequential.yaml",
    # Special cases
    "irrelevance": "irrelevance.yaml",
    "live_relevance": "live_relevance.yaml",
    # Multi-turn
    "multi_turn_base": "multi_turn_base.yaml",
    "multi_turn_composite": "multi_turn_composite.yaml",
    "multi_turn_long_context": "multi_turn_long_context.yaml",
    "multi_turn_miss_func": "multi_turn_miss_func.yaml",
    "multi_turn_miss_param": "multi_turn_miss_param.yaml",
    # Web Search
    "web_search": "web_search.yaml",
    # Direct Label Comparison
    "extracted_labels_results": "strict_label_match.yaml",
    "memory_kv": "memory_kv.yaml",

## Template Descriptions

- **simple_single_round.yaml**: Single function call with parameter matching
- **parallel_calls.yaml**: Multiple parallel calls (order-independent)
- **multiple_sequential.yaml**: Sequential multi-step calls
- **irrelevance.yaml**: No tools should be called
- **multi_turn_base.yaml**: Stateful multi-round filesystem operations
- **multi_turn_composite.yaml**: Complex composite multi-round tasks
- **multi_turn_long_context.yaml**: Long context retention scenarios
- **multi_turn_miss_func.yaml**: Missing tool handling
- **multi_turn_miss_param.yaml**: Missing parameter handling
- **live_relevance.yaml**: Tool selection relevance
