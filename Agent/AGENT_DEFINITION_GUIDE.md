# Agent Definition Guide - Agent定义完全指南

## 概述

Agent定义文件用于配置Agent的行为、能力和个性。框架通过 `agent_dir` 参数加载Agent定义。

## 文件格式

支持的文件格式：
- `.json` - JSON格式（单个或数组）
- `.jsonl` - JSON Lines格式（每行一个Agent定义）
- `.yaml` / `.yml` - YAML格式

## 加载机制

### 配置中的 agent_dir

```yaml
Agent:
  agent_dir: ./Agent/AgentBench/dbbench/Agent.jsonl
  # agent_dir 可以是:
  # 1. 文件路径 - 直接加载该文件
  # 2. 目录路径 - 加载目录下所有 .json/.jsonl/.yaml 文件
```

### 加载优先级

1. 首先查找 `agent_dir` 指定的路径
2. 如果是目录，按字母顺序加载所有配置文件
3. 如果是 `.jsonl` 文件：
   - 先尝试作为单个JSON对象解析
   - 失败则按行解析（每行一个Agent）
4. 第一个Agent定义成为 **Primary Agent**（主要Agent）
5. 其余Agent定义成为 **Managed Agents**（被管理的Agent）

### entry_agent_name

如果配置了 `entry_agent_name`，框架会将指定的Agent移到第一位：

```yaml
Agent:
  agent_dir: ./Agent/MultiAgent.jsonl
  entry_agent_name: Manager  # Manager将成为Primary Agent
```

---

## Agent定义字段说明

### 基础字段（所有Agent类型）

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Agent名称，用于标识和日志 |
| `description` | string | ❌ | Agent描述，会用作默认的instructions |
| `agent_type` | string | ❌ | Agent类型：`ToolCallingAgent`（默认）或 `CodeAgent` |
| `tools` | array | ❌ | 该Agent可用的工具名称列表 |

### 系统提示配置

有多种方式配置系统提示：

| 字段 | 类型 | 说明 |
|------|------|------|
| `instructions` | string | 直接指定系统提示文本（最高优先级）|
| `system_prompt` | string/path | 系统提示文本或文件路径 |
| `system_prompt_path` | path | 系统提示文件路径（已弃用）|
| `instructions_path` | path | 指令文件路径（已弃用）|

**优先级顺序：**
1. `instructions`
2. `system_prompt`
3. `system_prompt_path` / `instructions_path`
4. `description`（作为后备）

### ToolCallingAgent 专有字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prompt_templates` | dict/path | null | 提示模板（dict或YAML/JSON文件路径）|
| `stream_outputs` | boolean | false | 是否实时流式输出 |
| `max_tool_threads` | integer | 1 | 工具并行执行的最大线程数 |
| `managed_agents` | array | null | 被管理的子Agent列表（仅限ToolCallingAgent）|

### CodeAgent 专有字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `prompt_templates` | dict/path | null | 提示模板 |
| `additional_authorized_imports` | array | [] | 额外允许的Python导入模块 |
| `executor` | object | null | 自定义代码执行器 |
| `executor_type` | string | "python" | 执行器类型 |
| `executor_kwargs` | dict | {} | 执行器参数 |
| `max_print_outputs_length` | integer | 500 | 最大打印输出长度 |
| `stream_outputs` | boolean | false | 是否流式输出 |
| `use_structured_outputs_internally` | boolean | false | 内部使用结构化输出 |
| `code_block_tags` | list | ["```python", "```"] | 代码块标记 |

### 高级配置字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_steps` | integer | 20 | 最大执行步数 |
| `planning_interval` | integer | null | 规划间隔（步数），-1表示使用默认 |
| `add_base_tools` | boolean | true | 是否添加基础工具 |
| `verbosity_level` | integer | 1 | 日志详细程度（0-2）|
| `step_callbacks` | list | [] | 步骤回调函数列表 |
| `provide_run_summary` | boolean | false | 是否提供运行摘要 |
| `final_answer_checks` | boolean | true | 是否进行最终答案检查 |
| `return_full_result` | boolean | false | 是否返回完整结果 |
| `logger` | object | null | 自定义日志记录器 |

### 多Agent专有字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `node` | array | 该Agent管理的子Agent名称列表（层级结构）|

---

## 示例文件

### 1. 最简单的单Agent定义

**文件：Agent/simple_agent.jsonl**
```json
{"name": "Agent", "description": "A helpful assistant that can use tools to complete tasks."}
```

**说明：**
- 最小化配置
- 使用默认的 ToolCallingAgent
- 使用 description 作为系统提示
- 工具由 `fill_with_all_tools` 配置决定

---

### 2. 完整的单Agent定义

**文件：Agent/complete_agent.jsonl**
```json
{
  "name": "DatabaseAgent",
  "description": "Expert database query assistant",
  "agent_type": "ToolCallingAgent",
  "system_prompt": "You are an expert database administrator. You can query databases, analyze results, and provide insights. Always explain your SQL queries before executing them.",
  "tools": ["execute_sql", "describe_table", "show_tables"],
  "prompt_templates": "./Agent/templates/database_prompts.yaml",
  "max_steps": 15,
  "planning_interval": 3,
  "stream_outputs": true,
  "max_tool_threads": 1,
  "verbosity_level": 2,
  "provide_run_summary": true
}
```

**说明：**
- 完整配置所有常用参数
- 指定了具体的工具列表
- 使用自定义提示模板
- 配置了规划和日志级别

---

### 3. 使用外部系统提示文件

**文件：Agent/agent_with_prompt_file.jsonl**
```json
{
  "name": "ResearchAgent",
  "description": "Academic research assistant",
  "agent_type": "ToolCallingAgent",
  "system_prompt": "./Agent/prompts/research_assistant_prompt.txt",
  "tools": ["web_search", "read_paper", "summarize_text", "citation_lookup"]
}
```

**文件：Agent/prompts/research_assistant_prompt.txt**
```text
You are an expert academic research assistant specializing in computer science and AI.

Your capabilities:
- Search for academic papers and articles
- Read and analyze research papers
- Summarize complex technical content
- Look up citations and references

Your workflow:
1. Understand the research question
2. Search for relevant papers
3. Read and analyze key papers
4. Synthesize findings
5. Provide well-referenced answers

Always cite your sources and explain technical concepts clearly.
```

**说明：**
- system_prompt 指向文本文件路径
- 框架自动检测并加载文件内容
- 支持 .txt, .md 等文本文件

---

### 4. CodeAgent 示例

**文件：Agent/code_agent.jsonl**
```json
{
  "name": "DataAnalyst",
  "description": "Data analysis expert using Python",
  "agent_type": "CodeAgent",
  "system_prompt": "You are a data analyst. Write Python code to analyze data, create visualizations, and derive insights. Always test your code before finalizing.",
  "tools": ["load_data", "save_visualization"],
  "additional_authorized_imports": ["numpy", "pandas", "matplotlib", "seaborn", "scipy"],
  "max_print_outputs_length": 1000,
  "executor_type": "python",
  "stream_outputs": false,
  "max_steps": 20
}
```

**说明：**
- 使用 CodeAgent 类型
- 允许额外的Python导入
- 配置代码执行相关参数

---

### 5. 多Agent系统 - 平行协作

**文件：Agent/multi_agent_parallel.jsonl**
```json lines
{"name": "Coordinator", "description": "Coordinates multiple specialist agents", "tools": ["delegate_task", "aggregate_results"], "agent_type": "ToolCallingAgent"}
{"name": "SearchAgent", "description": "Searches for information", "tools": ["web_search", "query_database"], "agent_type": "ToolCallingAgent"}
{"name": "AnalysisAgent", "description": "Analyzes data and findings", "tools": ["analyze_data", "generate_report"], "agent_type": "ToolCallingAgent"}
{"name": "WriterAgent", "description": "Writes polished responses", "tools": ["format_text", "check_grammar"], "agent_type": "ToolCallingAgent"}
```

**配置：**
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/multi_agent_parallel.jsonl
  entry_agent_name: Coordinator
```

**说明：**
- 4个平行的Agent
- Coordinator作为主Agent（entry_agent）
- 其他Agent作为managed agents
- Coordinator可以调用其他Agent完成任务

---

### 6. 多Agent系统 - 层级结构

**文件：Agent/multi_agent_hierarchy.jsonl**
```json lines
{"name": "Manager", "description": "Project manager coordinating all teams", "tools": ["create_plan", "track_progress"], "node": ["DevTeam", "QATeam"]}
{"name": "DevTeam", "description": "Development team lead", "tools": ["write_code", "review_code"], "node": ["FrontendDev", "BackendDev"]}
{"name": "FrontendDev", "description": "Frontend developer", "tools": ["create_ui", "style_components"]}
{"name": "BackendDev", "description": "Backend developer", "tools": ["create_api", "setup_database"]}
{"name": "QATeam", "description": "Quality assurance team", "tools": ["write_tests", "run_tests", "report_bugs"]}
```

**说明：**
- 使用 `node` 字段定义层级关系
- Manager → DevTeam → {FrontendDev, BackendDev}
- Manager → QATeam
- 自动构建树状Agent结构

**生成的结构：**
```
Manager - Project manager coordinating all teams
├─ DevTeam - Development team lead
│  ├─ FrontendDev - Frontend developer
│  └─ BackendDev - Backend developer
└─ QATeam - Quality assurance team
```

---

### 7. 使用 prompt_templates 文件

**文件：Agent/agent_with_templates.jsonl**
```json
{
  "name": "CustomerSupportAgent",
  "description": "Customer support specialist",
  "agent_type": "ToolCallingAgent",
  "tools": ["search_policy", "create_ticket", "send_email"],
  "prompt_templates": "./Agent/templates/customer_support.yaml"
}
```

**文件：Agent/templates/customer_support.yaml**
```yaml
system_prompt: |
  You are a professional customer support agent.

  Your goals:
  - Help customers solve their problems quickly
  - Maintain a friendly and professional tone
  - Follow company policies
  - Escalate complex issues when needed

planning_prompt: |
  Break down the customer's issue into steps:
  1. Understand the problem
  2. Check relevant policies
  3. Provide a solution
  4. Follow up if needed

tool_calling_prompt: |
  Available tools:
  - search_policy: Look up company policies
  - create_ticket: Create a support ticket
  - send_email: Send email to customer

  Choose the most appropriate tool for the current step.

final_answer_prompt: |
  Provide a clear, concise answer to the customer.
  Include:
  - Solution to their problem
  - Any action items
  - Next steps if applicable
```

**说明：**
- prompt_templates 覆盖默认的提示词结构
- 支持 YAML 和 JSON 格式
- 可以自定义多个提示阶段

---

### 8. 混合格式示例（YAML）

**文件：Agent/agents_config.yaml**
```yaml
- name: PlannerAgent
  description: Strategic planning agent
  agent_type: ToolCallingAgent
  system_prompt: |
    You are a strategic planner. Break down complex tasks into actionable steps.
    Consider dependencies, priorities, and risks.
  tools:
    - analyze_requirements
    - create_roadmap
    - estimate_effort
  max_steps: 10
  planning_interval: 2

- name: ExecutorAgent
  description: Task execution specialist
  agent_type: ToolCallingAgent
  system_prompt: |
    You execute tasks according to plans.
    Follow instructions precisely and report progress.
  tools:
    - execute_task
    - report_progress
    - request_help
  max_steps: 25
  stream_outputs: true
```

**说明：**
- YAML格式更易读
- 支持多行字符串（system_prompt）
- 列表格式定义多个Agent

---

## 加载流程详解

### 步骤1：读取配置

```python
# 从config.yaml读取Agent配置
agent_settings = config.get("Agent", {})
agent_dir = agent_settings.get("agent_dir")
```

### 步骤2：加载Blueprint

```python
# 调用 load_agent_blueprints()
blueprints = load_agent_blueprints(agent_settings)

# 支持的文件类型：
# - .json: 单个Agent或数组
# - .jsonl: 每行一个Agent
# - .yaml/.yml: 单个Agent或数组
```

### 步骤3：处理entry_agent

```python
# 如果指定了entry_agent_name，重排序blueprints
entry_agent_name = agent_settings.get("entry_agent_name")
if entry_agent_name:
    # 将指定的Agent移到第一位
    blueprints = _prioritize_blueprints(blueprints, entry_agent_name)
```

### 步骤4：加载工具

```python
# 从Toolkit目录加载工具
tools = load_tools(config)
tool_map = {tool.name: tool for tool in tools}
```

### 步骤5：选择工具

```python
# 为每个Agent选择工具
if blueprint.get("tools"):
    # 使用blueprint中指定的工具
    selected_tools = [tool_map[name] for name in blueprint["tools"] if name in tool_map]
elif agent_settings.get("fill_with_all_tools", True):
    # 使用所有加载的工具
    selected_tools = list(tool_map.values())
else:
    # 不分配任何工具
    selected_tools = []
```

### 步骤6：构建Agent实例

```python
# 创建Agent实例
agent_class = ToolCallingAgent  # 或 CodeAgent
agent = agent_class(
    tools=selected_tools,
    model=model,
    name=blueprint.get("name"),
    instructions=system_prompt,
    **other_kwargs
)
```

### 步骤7：构建Agent层级

对于多Agent系统：
1. 如果有 `node` 字段，构建层级结构
2. 否则，第一个Agent作为Primary，其余作为Managed Agents
3. Primary Agent 可以调用 Managed Agents

---

## 字段优先级规则

### 系统提示（instructions）

优先级从高到低：
1. `instructions` 字段
2. `system_prompt` 字段（文件路径或文本）
3. `description` 字段（作为后备）
4. 全局 `Agent.system_prompt`（已弃用）

### Agent类型（agent_type）

优先级从高到低：
1. blueprint 中的 `agent_type`
2. 全局 `Agent.agent_type`
3. 默认值：`ToolCallingAgent`

### 工具列表（tools）

优先级从高到低：
1. blueprint 中的 `tools` 字段
2. 如果未指定且 `fill_with_all_tools=true`：使用所有工具
3. 如果 `fill_with_all_tools=false`：不分配工具

---

## 常见使用模式

### 模式1：单Agent单任务

```json
{"name": "Agent", "description": "Simple task executor", "tools": ["tool1", "tool2"]}
```

**配置：**
```yaml
Agent:
  type: single-agent
  agent_dir: ./Agent/single.jsonl
```

### 模式2：单Agent多轮对话

```json
{"name": "Assistant", "description": "Conversational assistant", "max_steps": 30}
```

**配置：**
```yaml
Agent:
  type: single-agent multi-round
  agent_dir: ./Agent/assistant.jsonl
```

### 模式3：多Agent协作（平行）

```json lines
{"name": "Coordinator", "tools": []}
{"name": "Agent1", "tools": ["tool_a"]}
{"name": "Agent2", "tools": ["tool_b"]}
```

**配置：**
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/parallel.jsonl
  entry_agent_name: Coordinator
```

### 模式4：多Agent协作（层级）

```json lines
{"name": "Manager", "node": ["Worker1", "Worker2"]}
{"name": "Worker1", "tools": ["task1"]}
{"name": "Worker2", "tools": ["task2"]}
```

**配置：**
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/hierarchy.jsonl
```

---

## 最佳实践

### 1. 命名规范

- **Agent名称**：使用 PascalCase（如 `DatabaseAgent`, `SearchCoordinator`）
- **描述**：简洁清晰，说明Agent的职责
- **文件名**：小写加下划线（如 `database_agent.jsonl`）

### 2. 系统提示设计

好的系统提示应该：
- ✅ 明确Agent的角色和职责
- ✅ 列出可用的能力和工具
- ✅ 提供行为准则和约束
- ✅ 包含示例或工作流程
- ❌ 不要过于冗长（保持在1000字以内）
- ❌ 不要包含任务特定的信息

**示例：**
```text
You are a SQL database expert.

Capabilities:
- Query databases using SQL
- Analyze query results
- Suggest optimizations

Guidelines:
- Always explain queries before executing
- Check for potential errors
- Provide clear explanations

Workflow:
1. Understand the question
2. Plan the SQL query
3. Execute and analyze
4. Provide insights
```

### 3. 工具分配策略

根据Agent的职责分配工具：

```json
{
  "name": "SpecialistAgent",
  "tools": ["specific_tool1", "specific_tool2"]  // ✅ 精确控制
}
```

vs

```json
{
  "name": "GeneralistAgent",
  "tools": null  // 依赖 fill_with_all_tools
}
```

**推荐：**
- 专业Agent：明确指定工具
- 通用Agent：使用 `fill_with_all_tools`

### 4. 多Agent设计原则

- **职责分离**：每个Agent有明确的专长
- **最小化通信**：减少Agent间不必要的交互
- **层级合理**：不要超过3层深度
- **避免循环**：检查 `node` 引用，避免循环依赖

### 5. 文件组织

推荐的目录结构：
```
Agent/
├── YourBenchmark/
│   ├── single_agent.jsonl        # 单Agent定义
│   ├── multi_agent.jsonl         # 多Agent定义
│   ├── prompts/                  # 系统提示文件
│   │   ├── agent1_prompt.txt
│   │   └── agent2_prompt.txt
│   └── templates/                # 提示模板
│       └── agent_templates.yaml
```

---

## 调试技巧

### 1. 查看加载的Agent

框架会打印加载的Agent信息：
```
Loading agent blueprints from: ./Agent/multi_agent.jsonl
Loaded 3 agent blueprints
Primary agent: Manager
Managed agents: [Agent1, Agent2]
```

### 2. 验证工具分配

检查日志确认工具正确加载：
```
Agent 'DatabaseAgent' assigned tools: ['execute_sql', 'describe_table']
Warning: Tool 'unknown_tool' not found; skipping
```

### 3. 多Agent层级可视化

多Agent系统会打印层级结构：
```
Multi-agent hierarchy:
Manager - Project coordinator
├─ DevAgent - Development specialist
│  └─ CodeReviewer - Code review expert
└─ TestAgent - Testing specialist
```

### 4. 常见错误

**错误1：Agent定义文件不存在**
```
Warning: Agent configuration path ./Agent/missing.jsonl does not exist.
Falling back to default agent settings.
```
**解决**：检查路径是否正确

**错误2：工具未找到**
```
Warning: Tool 'missing_tool' not found among loaded tools; skipping.
```
**解决**：确认工具在Toolkit中定义并加载

**错误3：JSON格式错误**
```
Warning: Failed to load agent blueprint from ./Agent/bad.jsonl: Expecting property name enclosed in double quotes
```
**解决**：检查JSON语法

**错误4：循环依赖**
```
Warning: Cycle detected in agent hierarchy (A -> B -> A); skipping recursive attachment.
```
**解决**：修改 `node` 字段，消除循环

---

## 附录：完整字段参考

### ToolCallingAgent 支持的字段

```json
{
  "name": "string",
  "description": "string",
  "agent_type": "ToolCallingAgent",
  "tools": ["string"],
  "instructions": "string",
  "system_prompt": "string or path",
  "prompt_templates": "dict or path",
  "max_steps": "integer",
  "add_base_tools": "boolean",
  "verbosity_level": "integer",
  "managed_agents": "array",
  "step_callbacks": "array",
  "planning_interval": "integer",
  "provide_run_summary": "boolean",
  "final_answer_checks": "boolean",
  "return_full_result": "boolean",
  "logger": "object",
  "stream_outputs": "boolean",
  "max_tool_threads": "integer",
  "node": ["string"]
}
```

### CodeAgent 支持的字段

```json
{
  "name": "string",
  "description": "string",
  "agent_type": "CodeAgent",
  "tools": ["string"],
  "instructions": "string",
  "system_prompt": "string or path",
  "prompt_templates": "dict or path",
  "max_steps": "integer",
  "add_base_tools": "boolean",
  "verbosity_level": "integer",
  "managed_agents": "array",
  "step_callbacks": "array",
  "planning_interval": "integer",
  "provide_run_summary": "boolean",
  "final_answer_checks": "boolean",
  "return_full_result": "boolean",
  "logger": "object",
  "additional_authorized_imports": ["string"],
  "executor": "object",
  "executor_type": "string",
  "executor_kwargs": "dict",
  "max_print_outputs_length": "integer",
  "stream_outputs": "boolean",
  "use_structured_outputs_internally": "boolean",
  "code_block_tags": ["string"]
}
```

---

**文档版本**: v1.0
**最后更新**: 2024-01-28
**维护者**: Agent Sandbox Team
