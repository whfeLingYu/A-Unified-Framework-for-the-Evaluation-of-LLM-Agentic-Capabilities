# Agent Blueprint 加载机制详解

## 概述

`_load_blueprints_from_file` 函数是Agent定义加载的核心函数，负责将各种格式的Agent定义文件解析为Python字典列表（blueprints）。

---

## 函数签名

```python
def _load_blueprints_from_file(path: Path) -> List[Dict[str, Any]]:
    """
    从文件加载Agent blueprints（蓝图）。

    参数:
        path: Path - Agent定义文件的路径对象

    返回:
        List[Dict[str, Any]] - Agent定义字典列表

    支持格式:
        - .json: JSON对象或数组
        - .jsonl: JSON Lines (每行一个对象)
        - .yaml/.yml: YAML对象或数组
    """
```

---

## 参数详解

### path: Path

**类型**: `pathlib.Path` 对象

**说明**:
- Agent定义文件的绝对或相对路径
- 必须是文件路径（不是目录）
- 文件必须存在且可读
- 扩展名决定解析方式

**支持的扩展名**:
- `.json` - JSON格式
- `.jsonl` - JSON Lines格式
- `.yaml` - YAML格式
- `.yml` - YAML格式

**示例**:
```python
from pathlib import Path

# 绝对路径
path = Path("/Users/username/Agent/my_agent.jsonl")

# 相对路径
path = Path("./Agent/database_agent.json")

# 使用expanduser处理~
path = Path("~/project/Agent/agent.yaml").expanduser()
```

---

## 返回值详解

### List[Dict[str, Any]]

**类型**: 字典列表

**结构**: 每个字典代表一个Agent的定义（blueprint）

**字典键值**:
```python
{
    "name": str,                    # Agent名称（必需）
    "description": str,             # Agent描述（可选）
    "agent_type": str,              # Agent类型（可选）
    "tools": List[str],             # 工具列表（可选）
    "system_prompt": str,           # 系统提示（可选）
    "max_steps": int,               # 最大步数（可选）
    "planning_interval": int,       # 规划间隔（可选）
    "node": List[str],              # 子Agent列表（可选）
    # ... 其他Agent配置字段
}
```

**返回示例**:
```python
# 单个Agent
[
    {
        "name": "DatabaseAgent",
        "description": "SQL expert",
        "tools": ["execute_sql", "describe_table"]
    }
]

# 多个Agent
[
    {"name": "Manager", "node": ["Worker1", "Worker2"]},
    {"name": "Worker1", "tools": ["task1"]},
    {"name": "Worker2", "tools": ["task2"]}
]

# 空文件
[]
```

---

## 加载流程详解

### 1. 文件类型检测

```python
if path.suffix.lower() == ".jsonl":
    # JSONL特殊处理
    处理JSONL格式
else:
    # JSON/YAML统一处理
    根据扩展名选择解析器
```

### 2. JSONL格式处理

JSONL有两种可能的格式：

**格式A: 单个JSON对象（罕见）**
```json
{"name": "Agent", "description": "Single agent in jsonl file"}
```

**格式B: 多行JSON对象（常见）**
```json
{"name": "Agent1", "description": "First agent"}
{"name": "Agent2", "description": "Second agent"}
{"name": "Agent3", "description": "Third agent"}
```

**处理逻辑**:
```python
# 1. 先尝试整体解析（格式A）
try:
    data = json.loads(content)
    # 成功 → 返回 [data]
except json.JSONDecodeError:
    # 2. 失败则按行解析（格式B）
    blueprints = []
    for line in file:
        if line.strip():
            blueprints.append(json.loads(line))
    return blueprints
```

### 3. JSON格式处理

**格式A: 单个对象**
```json
{
    "name": "Agent",
    "description": "Single agent"
}
```
返回: `[{"name": "Agent", ...}]`

**格式B: 对象数组**
```json
[
    {"name": "Agent1", "description": "First"},
    {"name": "Agent2", "description": "Second"}
]
```
返回: `[{"name": "Agent1", ...}, {"name": "Agent2", ...}]`

### 4. YAML格式处理

**格式A: 单个对象**
```yaml
name: Agent
description: Single agent
tools:
  - tool1
  - tool2
```
返回: `[{"name": "Agent", ...}]`

**格式B: 对象列表**
```yaml
- name: Agent1
  description: First agent
- name: Agent2
  description: Second agent
```
返回: `[{"name": "Agent1", ...}, {"name": "Agent2", ...}]`

---

## 完整示例

### 示例1: JSON单个对象

**文件: agent.json**
```json
{
    "name": "DatabaseExpert",
    "description": "SQL database specialist",
    "agent_type": "ToolCallingAgent",
    "tools": ["execute_sql", "describe_table", "show_tables"],
    "system_prompt": "You are a database expert. Help users query and analyze databases.",
    "max_steps": 20,
    "planning_interval": 3
}
```

**加载过程**:
```python
# 1. 调用函数
path = Path("./Agent/agent.json")
blueprints = _load_blueprints_from_file(path)

# 2. 解析过程
# - 检测到 .json 扩展名
# - 使用 json.load() 读取文件
# - 得到单个 dict 对象
# - 包装成列表返回

# 3. 返回结果
blueprints = [
    {
        "name": "DatabaseExpert",
        "description": "SQL database specialist",
        "agent_type": "ToolCallingAgent",
        "tools": ["execute_sql", "describe_table", "show_tables"],
        "system_prompt": "You are a database expert...",
        "max_steps": 20,
        "planning_interval": 3
    }
]

# 4. 后续使用
primary_blueprint = blueprints[0]  # 第一个成为primary agent
agent_name = primary_blueprint["name"]  # "DatabaseExpert"
agent_tools = primary_blueprint["tools"]  # ["execute_sql", ...]
```

---

### 示例2: JSON数组

**文件: multi_agents.json**
```json
[
    {
        "name": "Coordinator",
        "description": "Coordinates specialist agents",
        "tools": ["delegate_task", "collect_results"],
        "max_steps": 15
    },
    {
        "name": "SearchAgent",
        "description": "Information search specialist",
        "tools": ["web_search", "database_query"],
        "max_steps": 10
    },
    {
        "name": "AnalysisAgent",
        "description": "Data analysis specialist",
        "tools": ["analyze_data", "create_chart"],
        "max_steps": 12
    }
]
```

**加载过程**:
```python
# 1. 调用函数
path = Path("./Agent/multi_agents.json")
blueprints = _load_blueprints_from_file(path)

# 2. 解析过程
# - 检测到 .json 扩展名
# - 使用 json.load() 读取
# - 得到 list[dict] 对象
# - 直接返回（已经是列表）

# 3. 返回结果
blueprints = [
    {
        "name": "Coordinator",
        "description": "Coordinates specialist agents",
        "tools": ["delegate_task", "collect_results"],
        "max_steps": 15
    },
    {
        "name": "SearchAgent",
        "description": "Information search specialist",
        "tools": ["web_search", "database_query"],
        "max_steps": 10
    },
    {
        "name": "AnalysisAgent",
        "description": "Data analysis specialist",
        "tools": ["analyze_data", "create_chart"],
        "max_steps": 12
    }
]

# 4. 后续使用
primary = blueprints[0]  # Coordinator
managed = blueprints[1:]  # [SearchAgent, AnalysisAgent]

for bp in blueprints:
    print(f"Agent: {bp['name']}, Tools: {bp['tools']}")
```

---

### 示例3: JSONL格式（每行一个对象）

**文件: hierarchy.jsonl**
```json
{"name": "Manager", "description": "Project manager", "tools": ["plan", "assign"], "node": ["DevLead", "QALead"]}
{"name": "DevLead", "description": "Development lead", "tools": ["review_code"], "node": ["Developer"]}
{"name": "Developer", "description": "Software developer", "tools": ["write_code", "test_code"]}
{"name": "QALead", "description": "QA lead", "tools": ["create_test_plan"], "node": ["QAEngineer"]}
{"name": "QAEngineer", "description": "QA engineer", "tools": ["run_tests", "report_bugs"]}
```

**加载过程**:
```python
# 1. 调用函数
path = Path("./Agent/hierarchy.jsonl")
blueprints = _load_blueprints_from_file(path)

# 2. 解析过程
# - 检测到 .jsonl 扩展名
# - 读取全部内容
# - 尝试整体解析 → 失败（不是单个JSON）
# - 按行解析：
#   - 跳过空行
#   - 每行 json.loads() 得到一个 dict
#   - 收集所有 dict 到列表

# 3. 返回结果
blueprints = [
    {"name": "Manager", "description": "Project manager",
     "tools": ["plan", "assign"], "node": ["DevLead", "QALead"]},
    {"name": "DevLead", "description": "Development lead",
     "tools": ["review_code"], "node": ["Developer"]},
    {"name": "Developer", "description": "Software developer",
     "tools": ["write_code", "test_code"]},
    {"name": "QALead", "description": "QA lead",
     "tools": ["create_test_plan"], "node": ["QAEngineer"]},
    {"name": "QAEngineer", "description": "QA engineer",
     "tools": ["run_tests", "report_bugs"]}
]

# 4. 构建层级关系
# 通过 node 字段构建树状结构:
# Manager
# ├─ DevLead
# │  └─ Developer
# └─ QALead
#    └─ QAEngineer
```

---

### 示例4: YAML单个对象

**文件: agent.yaml**
```yaml
name: ResearchAssistant
description: Academic research assistant
agent_type: ToolCallingAgent

system_prompt: |
  You are an academic research assistant.
  Help users find papers, analyze research, and synthesize findings.

tools:
  - search_arxiv
  - read_paper
  - summarize_text
  - extract_citations

max_steps: 25
planning_interval: 5
stream_outputs: false
verbosity_level: 2
```

**加载过程**:
```python
# 1. 调用函数
path = Path("./Agent/agent.yaml")
blueprints = _load_blueprints_from_file(path)

# 2. 解析过程
# - 检测到 .yaml 扩展名
# - 使用 yaml.safe_load() 读取
# - 得到单个 dict 对象
# - 包装成列表返回

# 3. 返回结果
blueprints = [
    {
        "name": "ResearchAssistant",
        "description": "Academic research assistant",
        "agent_type": "ToolCallingAgent",
        "system_prompt": "You are an academic research assistant.\nHelp users find papers...",
        "tools": ["search_arxiv", "read_paper", "summarize_text", "extract_citations"],
        "max_steps": 25,
        "planning_interval": 5,
        "stream_outputs": False,
        "verbosity_level": 2
    }
]

# 4. 后续使用
bp = blueprints[0]
# YAML的多行字符串 | 保持换行符
system_prompt_lines = bp["system_prompt"].split("\n")
```

---

### 示例5: YAML对象列表

**文件: agents.yaml**
```yaml
# Agent 1: Planner
- name: PlannerAgent
  description: Strategic planning specialist
  agent_type: ToolCallingAgent
  system_prompt: |
    You are a strategic planner.
    Break down complex tasks into actionable steps.
  tools:
    - analyze_requirements
    - create_roadmap
  max_steps: 10

# Agent 2: Executor
- name: ExecutorAgent
  description: Task execution specialist
  agent_type: ToolCallingAgent
  system_prompt: Execute tasks according to plans.
  tools:
    - execute_task
    - report_progress
  max_steps: 20
  stream_outputs: true
```

**加载过程**:
```python
# 1. 调用函数
path = Path("./Agent/agents.yaml")
blueprints = _load_blueprints_from_file(path)

# 2. 解析过程
# - 检测到 .yaml 扩展名
# - 使用 yaml.safe_load() 读取
# - 得到 list[dict] 对象（因为YAML开头是 -）
# - 直接返回

# 3. 返回结果
blueprints = [
    {
        "name": "PlannerAgent",
        "description": "Strategic planning specialist",
        "agent_type": "ToolCallingAgent",
        "system_prompt": "You are a strategic planner.\nBreak down complex tasks...",
        "tools": ["analyze_requirements", "create_roadmap"],
        "max_steps": 10
    },
    {
        "name": "ExecutorAgent",
        "description": "Task execution specialist",
        "agent_type": "ToolCallingAgent",
        "system_prompt": "Execute tasks according to plans.",
        "tools": ["execute_task", "report_progress"],
        "max_steps": 20,
        "stream_outputs": True
    }
]

# 4. 后续使用
planner = blueprints[0]
executor = blueprints[1]
```

---

## 完整调用链路

### 从配置文件到Agent实例

```python
# ============================================
# 1. 读取配置文件
# ============================================
config = read_config("config.yaml")
# config = {
#     "Agent": {
#         "agent_dir": "./Agent/my_agents.jsonl",
#         "type": "multi-agent",
#         "entry_agent_name": "Manager"
#     },
#     ...
# }

# ============================================
# 2. 加载Agent blueprints
# ============================================
agent_settings = config.get("Agent", {})
blueprints = load_agent_blueprints(agent_settings)

# load_agent_blueprints 内部调用:
def load_agent_blueprints(agent_settings):
    agent_dir = agent_settings.get("agent_dir")
    path = Path(agent_dir).expanduser()

    if path.is_file():
        # 调用我们讲解的函数
        return _load_blueprints_from_file(path)
    elif path.is_dir():
        # 目录：加载所有文件
        blueprints = []
        for file_path in sorted(path.iterdir()):
            if file_path.suffix in {".json", ".jsonl", ".yaml", ".yml"}:
                blueprints.extend(_load_blueprints_from_file(file_path))
        return blueprints

# blueprints = [
#     {"name": "Manager", "node": ["Worker1", "Worker2"], ...},
#     {"name": "Worker1", "tools": ["task1"], ...},
#     {"name": "Worker2", "tools": ["task2"], ...}
# ]

# ============================================
# 3. 处理 entry_agent_name
# ============================================
entry_agent_name = agent_settings.get("entry_agent_name")
if entry_agent_name:
    blueprints = _prioritize_blueprints(blueprints, entry_agent_name)
    # 将 "Manager" 移到第一位

# blueprints = [
#     {"name": "Manager", ...},  # 现在在第一位
#     {"name": "Worker1", ...},
#     {"name": "Worker2", ...}
# ]

# ============================================
# 4. 加载工具
# ============================================
tools = load_tools(config)
tool_map = {tool.name: tool for tool in tools}
# tool_map = {
#     "task1": Task1Tool(),
#     "task2": Task2Tool(),
#     ...
# }

# ============================================
# 5. 为每个blueprint选择工具
# ============================================
for blueprint in blueprints:
    if blueprint.get("tools"):
        # 使用blueprint指定的工具
        selected = [tool_map[name] for name in blueprint["tools"] if name in tool_map]
    elif agent_settings.get("fill_with_all_tools", True):
        # 使用所有工具
        selected = list(tool_map.values())
    else:
        # 不分配工具
        selected = []

    blueprint["_selected_tools"] = selected

# ============================================
# 6. 创建Agent实例
# ============================================
model = create_model(config)  # 创建语言模型

# 创建Primary Agent（第一个blueprint）
primary_blueprint = blueprints[0]
primary_agent = ToolCallingAgent(
    tools=primary_blueprint["_selected_tools"],
    model=model,
    name=primary_blueprint["name"],
    instructions=primary_blueprint.get("system_prompt"),
    max_steps=primary_blueprint.get("max_steps", 20),
    # ... 其他参数
)

# 创建Managed Agents（其余blueprints）
managed_agents = []
for blueprint in blueprints[1:]:
    agent = ToolCallingAgent(
        tools=blueprint["_selected_tools"],
        model=model,
        name=blueprint["name"],
        instructions=blueprint.get("system_prompt"),
        # ... 其他参数
    )
    managed_agents.append(agent)

# 将managed agents附加到primary agent
if managed_agents:
    primary_agent.managed_agents = managed_agents

# ============================================
# 7. 返回Agent Bundle
# ============================================
return AgentBundle(
    mode="multi-agent",
    primary=primary_agent,
    managed=managed_agents,
    blueprints=blueprints,
    agent_settings=agent_settings,
    model=model,
    tool_map=tool_map
)
```

---

## 错误处理

### 1. 文件不存在

```python
path = Path("./Agent/missing.jsonl")
# FileNotFoundError 或返回空列表
```

**框架处理**:
```python
if not path.exists():
    print(f"Warning: Agent config path {path} does not exist.")
    return []
```

### 2. JSON语法错误

**文件: bad.json**
```json
{
    "name": "Agent",
    "tools": ["tool1", "tool2",]  // 末尾多余逗号
}
```

**错误信息**:
```
Warning: Failed to load agent blueprint from ./Agent/bad.json:
Expecting property name enclosed in double quotes
```

### 3. JSONL格式错误

**文件: bad.jsonl**
```json
{"name": "Agent1"}
{"name": "Agent2"  // 缺少右括号
{"name": "Agent3"}
```

**错误处理**:
```python
# 会在解析第二行时失败
# 只返回成功解析的行
blueprints = [{"name": "Agent1"}]  # 只有第一行
```

### 4. 不支持的文件类型

```python
path = Path("./Agent/config.txt")
# 不会被加载（扩展名不匹配）
```

---

## 性能考虑

### 文件大小影响

| 文件大小 | Agent数量 | 加载时间 | 建议 |
|---------|----------|---------|------|
| < 1KB | 1-5 | < 1ms | 无问题 |
| 1-10KB | 5-50 | 1-10ms | 无问题 |
| 10-100KB | 50-500 | 10-100ms | 考虑拆分 |
| > 100KB | > 500 | > 100ms | 建议拆分为多个文件 |

### 格式性能对比

| 格式 | 解析速度 | 内存占用 | 推荐场景 |
|------|---------|---------|----------|
| JSON | 快 | 低 | 单个或少量Agent |
| JSONL | 中 | 低 | 多个Agent（推荐）|
| YAML | 慢 | 中 | 配置复杂需要注释 |

### 优化建议

1. **多Agent使用JSONL**: 每行一个Agent，易于编辑和合并
2. **简单场景使用JSON**: 单个Agent或少量Agent
3. **复杂配置使用YAML**: 需要注释和多行字符串
4. **避免超大文件**: 超过100个Agent考虑拆分

---

## 调试技巧

### 1. 验证JSON/YAML语法

```bash
# 验证JSON
python -c "import json; json.load(open('agent.json'))"

# 验证YAML
python -c "import yaml; yaml.safe_load(open('agent.yaml'))"

# 使用在线工具
# JSON: https://jsonlint.com/
# YAML: https://www.yamllint.com/
```

### 2. 检查加载结果

```python
from pathlib import Path
from Utils.agent_utils import load_agent_blueprints

# 加载并打印
config = {"Agent": {"agent_dir": "./Agent/my_agents.jsonl"}}
blueprints = load_agent_blueprints(config["Agent"])

print(f"Loaded {len(blueprints)} agent(s):")
for i, bp in enumerate(blueprints):
    print(f"  {i+1}. {bp.get('name', 'Unnamed')}")
    print(f"     Tools: {bp.get('tools', [])}")
    print(f"     Type: {bp.get('agent_type', 'default')}")
```

### 3. 查看详细日志

在配置中启用详细日志：

```yaml
Agent:
  agent_dir: ./Agent/agents.jsonl
  verbosity_level: 2  # 0=quiet, 1=normal, 2=verbose
```

日志输出示例：
```
Loading agent blueprints from: ./Agent/agents.jsonl
Loaded 3 agent blueprints
Primary agent: Manager
  - Tools: ['delegate', 'collect']
  - Type: ToolCallingAgent
Managed agents: [Worker1, Worker2]
  Worker1:
    - Tools: ['task1']
  Worker2:
    - Tools: ['task2']
```

---

## 常见问题

### Q1: 为什么我的JSONL文件只加载了第一行？

**原因**: 文件可能被解析为单个JSON对象。

**检查**:
```python
import json
with open("your.jsonl", "r") as f:
    content = f.read().strip()
    try:
        obj = json.loads(content)
        print("File is parsed as single JSON object")
    except json.JSONDecodeError:
        print("File needs line-by-line parsing")
```

**解决**: 确保每行都是独立的JSON对象，没有外层的 `[` `]`。

### Q2: YAML数组和对象有什么区别？

**对象（返回单个Agent）:**
```yaml
name: Agent
tools: [tool1, tool2]
```

**数组（返回多个Agent）:**
```yaml
- name: Agent1
  tools: [tool1]
- name: Agent2
  tools: [tool2]
```

关键是开头的 `-`。

### Q3: 如何在一个目录中加载多个文件？

```python
# 配置指向目录
Agent:
  agent_dir: ./Agent/my_agents/  # 注意是目录

# 目录结构
Agent/my_agents/
├── agent1.json
├── agent2.jsonl
└── agent3.yaml

# 所有文件都会被加载并合并
```

### Q4: blueprint的字段优先级是什么？

当blueprint和全局配置都定义了同一字段时：

1. **blueprint字段优先**（特定覆盖通用）
2. 如果blueprint没有，使用全局设置
3. 如果都没有，使用默认值

```python
# config.yaml
Agent:
  max_steps: 20  # 全局默认

# agent.json
{"name": "Agent", "max_steps": 30}  # 特定值

# 结果: 该Agent使用 max_steps=30
```

---

## 总结

### 核心要点

1. **函数作用**: 解析Agent定义文件为字典列表
2. **输入参数**: `Path` 对象指向文件
3. **返回值**: `List[Dict[str, Any]]` - Agent定义列表
4. **支持格式**: JSON, JSONL, YAML
5. **容错性**: 失败返回空列表，打印警告

### 推荐实践

- ✅ **单Agent**: 使用 `.json` 或 `.yaml`
- ✅ **多Agent**: 使用 `.jsonl`（每行一个Agent）
- ✅ **复杂配置**: 使用 `.yaml`（支持注释和多行字符串）
- ✅ **大量Agent**: 拆分到多个文件，使用目录

### 下一步

- 查看 [AGENT_DEFINITION_GUIDE.md](./AGENT_DEFINITION_GUIDE.md) 了解完整字段
- 参考 [examples/](./examples/) 目录中的示例文件
- 阅读 [CONFIG_GUIDE_CN.md](../Config/CONFIG_GUIDE_CN.md) 了解配置集成

---

**文档版本**: v1.0
**最后更新**: 2024-01-28
**相关函数**: `load_agent_blueprints`, `create_agent_instance`, `_build_agent_hierarchy`
