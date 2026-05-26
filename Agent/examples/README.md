# Agent Definition Examples

This directory contains example Agent definition files demonstrating various configuration patterns.

## 📁 File Overview

| File | Type | Description |
|------|------|-------------|
| `01_minimal_agent.jsonl` | Single | Simplest possible agent definition |
| `02_complete_single_agent.jsonl` | Single | Fully configured single agent with all options |
| `03_code_agent.jsonl` | Single | CodeAgent for Python data analysis |
| `04_multi_agent_parallel.jsonl` | Multi | 4 agents working in parallel (coordinator pattern) |
| `05_multi_agent_hierarchy.jsonl` | Multi | 6 agents in hierarchical structure (tree) |
| `06_agent_with_prompt_file.jsonl` | Single | Agent loading system prompt from external file |
| `07_agent_with_templates.yaml` | Single | YAML format with prompt templates |

## 🚀 How to Use

### Using an Example Agent

1. **Copy the example:**
   ```bash
   cp Agent/examples/02_complete_single_agent.jsonl Agent/my_agent.jsonl
   ```

2. **Modify for your needs:**
   - Change `name` and `description`
   - Update `tools` list
   - Customize `system_prompt`

3. **Reference in config:**
   ```yaml
   Agent:
     type: single-agent
     agent_dir: ./Agent/my_agent.jsonl
     agent_type: ToolCallingAgent
   ```

4. **Run:**
   ```bash
   python main.py --config your_config.yaml
   ```

## 📚 Example Descriptions

### 01_minimal_agent.jsonl
The absolute minimum agent definition. Uses defaults for everything.

**Use when:**
- Quick prototyping
- Testing framework
- You want framework defaults

**Config:**
```yaml
Agent:
  type: single-agent
  agent_dir: ./Agent/examples/01_minimal_agent.jsonl
  fill_with_all_tools: true
```

---

### 02_complete_single_agent.jsonl
Comprehensive single agent with all ToolCallingAgent options configured.

**Features:**
- Explicit system prompt
- Specific tool list
- Planning configuration
- Streaming enabled
- Verbosity and summary options

**Use when:**
- Production deployments
- Need fine control
- Complex single-agent tasks

**Config:**
```yaml
Agent:
  type: single-agent multi-round
  agent_dir: ./Agent/examples/02_complete_single_agent.jsonl
```

---

### 03_code_agent.jsonl
CodeAgent that writes and executes Python code for data analysis.

**Features:**
- Uses CodeAgent instead of ToolCallingAgent
- Allows specific Python imports
- Configures code execution
- Longer output limits

**Use when:**
- Data analysis tasks
- Scientific computing
- Complex calculations
- Visualization needs

**Config:**
```yaml
Agent:
  type: single-agent
  agent_dir: ./Agent/examples/03_code_agent.jsonl
  agent_type: CodeAgent
```

**Note:** Requires tools that provide data access (load_csv, read_file, etc.)

---

### 04_multi_agent_parallel.jsonl
Four agents working together: Coordinator + 3 specialists.

**Structure:**
```
Coordinator (primary)
├─ SearchAgent (managed)
├─ AnalysisAgent (managed)
└─ WriterAgent (managed)
```

**Use when:**
- Tasks need different specializations
- Divide-and-conquer approach
- Parallel execution beneficial

**Config:**
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/examples/04_multi_agent_parallel.jsonl
  entry_agent_name: Coordinator
```

**Tools needed:**
- delegate_to_agent
- get_agent_result
- web_search, database_query, document_search
- analyze_data, compute_statistics, create_chart
- format_markdown, create_summary, proofread

---

### 05_multi_agent_hierarchy.jsonl
Six agents in a tree structure mimicking a dev team.

**Structure:**
```
ProjectManager (root)
├─ DevLead
│  ├─ FrontendDev
│  └─ BackendDev
└─ QALead
   └─ QAEngineer
```

**Features:**
- Uses `node` field for hierarchy
- 3-level depth
- Realistic team structure
- Different tools per role

**Use when:**
- Complex projects with clear roles
- Workflow has stages
- Need delegation chains

**Config:**
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/examples/05_multi_agent_hierarchy.jsonl
  entry_agent_name: ProjectManager  # Optional, auto-detected
```

---

### 06_agent_with_prompt_file.jsonl
Agent loading system prompt from external text file.

**Structure:**
```
Agent/examples/
├─ 06_agent_with_prompt_file.jsonl  (references prompt file)
└─ prompts/
   └─ customer_support_prompt.txt   (actual prompt content)
```

**Benefits:**
- Cleaner JSON structure
- Easy prompt editing
- Version control friendly
- Reusable prompts

**Use when:**
- Long system prompts
- Shared prompts across agents
- Frequent prompt iterations

---

### 07_agent_with_templates.yaml
YAML format with external prompt templates.

**Structure:**
```
Agent/examples/
├─ 07_agent_with_templates.yaml      (references template)
└─ templates/
   └─ research_assistant_templates.yaml  (detailed prompts)
```

**Features:**
- YAML format (more readable)
- Multi-line strings with `|`
- Lists without quotes
- References template file

**Template includes:**
- planning_prompt
- tool_calling_prompt
- final_answer_prompt
- error_prompt

**Use when:**
- Complex prompt engineering
- Multiple prompt stages
- Prefer YAML over JSON

---

## 🔧 Customization Tips

### Adjusting Tools

```json
{
  "name": "MyAgent",
  "tools": ["tool1", "tool2"]  // Only these tools
}
```

Or let config decide:
```json
{
  "name": "MyAgent"
  // No tools field → use fill_with_all_tools setting
}
```

### Adjusting Verbosity

```json
{
  "verbosity_level": 0  // Quiet (errors only)
  "verbosity_level": 1  // Normal (default)
  "verbosity_level": 2  // Verbose (debug info)
}
```

### Adjusting Steps

```json
{
  "max_steps": 10  // Quick tasks
  "max_steps": 20  // Default
  "max_steps": 50  // Complex tasks
}
```

### Planning Frequency

```json
{
  "planning_interval": -1   // Use default
  "planning_interval": null  // No planning
  "planning_interval": 3     // Plan every 3 steps
  "planning_interval": 10    // Plan every 10 steps
}
```

---

## 🧪 Testing Examples

### Test Single Agent
```bash
# Test minimal agent
python main.py --config config_minimal_test.yaml --task "What is 1+1?"

# Test complete agent
python main.py --config config_complete_test.yaml --benchmark test_tasks.jsonl
```

### Test Multi-Agent
```bash
# Test parallel agents
python main.py --config config_parallel_test.yaml

# Test hierarchy
python main.py --config config_hierarchy_test.yaml
```

### Verify Loading
```bash
# Add --verbose to see agent loading details
python main.py --config your_config.yaml --verbose
```

Look for:
```
Loading agent blueprints from: ./Agent/examples/02_complete_single_agent.jsonl
Loaded 1 agent blueprint(s)
Primary agent: DatabaseExpert
Agent 'DatabaseExpert' assigned tools: ['execute_sql', 'describe_table', 'show_tables', 'show_columns']
```

---

## 📖 Related Documentation

- **[AGENT_DEFINITION_GUIDE.md](../AGENT_DEFINITION_GUIDE.md)** - Complete reference
- **[Config Guide](../../Config/CONFIG_GUIDE_CN.md)** - Configuration documentation
- **[Tool Development](../../Toolkit/README.md)** - Creating custom tools

---

## 🤔 FAQs

**Q: Can I mix .json and .jsonl files?**
A: Yes, put them in a directory and set `agent_dir` to that directory. All will be loaded.

**Q: What if two agents have the same name?**
A: The second one will overwrite the first. Use unique names.

**Q: Can I change agent_type per agent in multi-agent?**
A: Yes! Each agent can specify its own `agent_type` field.

**Q: How do I see the actual prompt used?**
A: Set `verbosity_level: 2` in the agent definition or check logs.

**Q: Can I use environment variables in prompts?**
A: Not directly. You'd need to process the file before loading or use a template engine.

---

**Last Updated**: 2024-01-28
**Framework Version**: 1.0+
