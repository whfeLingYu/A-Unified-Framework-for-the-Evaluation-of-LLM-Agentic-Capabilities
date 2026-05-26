# Agent Blueprint 加载流程图

## 完整加载流程

```
┌─────────────────────────────────────────────────────────────┐
│                     开始: 配置文件                            │
│                    config.yaml                               │
│                                                              │
│  Agent:                                                      │
│    agent_dir: ./Agent/my_agents.jsonl                       │
│    type: multi-agent                                         │
│    entry_agent_name: Manager                                │
│    fill_with_all_tools: false                               │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 1: 读取Agent配置                                 │
│         agent_settings = config.get("Agent", {})            │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 2: 获取agent_dir路径                            │
│         agent_dir = agent_settings.get("agent_dir")         │
│         path = Path(agent_dir).expanduser()                 │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 3: 判断路径类型                                  │
│              path.exists()?                                  │
└──┬──────────────────────────────────────────────┬──────────┘
   │ 否                                             │ 是
   ↓                                                ↓
┌────────────────┐                    ┌──────────────────────────┐
│  返回空列表 []   │                    │   path.is_file()?        │
│  打印警告       │                    └───┬──────────────────┬───┘
└────────────────┘                        │ 是                │ 否
                                         ↓                   ↓
                            ┌──────────────────────┐  ┌────────────────┐
                            │  调用函数:            │  │  path.is_dir() │
                            │  _load_blueprints_   │  │  遍历目录       │
                            │   from_file(path)    │  │  加载所有文件   │
                            └──────────┬───────────┘  └───────┬────────┘
                                      │                       │
                                      └───────┬───────────────┘
                                              ↓
┌─────────────────────────────────────────────────────────────┐
│         _load_blueprints_from_file 函数内部                  │
│         (核心加载逻辑)                                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         检查文件扩展名                                         │
│         path.suffix.lower()                                 │
└──┬────────────────┬─────────────────┬──────────────────────┘
   │ .jsonl         │ .json            │ .yaml / .yml
   ↓                ↓                  ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│  JSONL处理    │ │  JSON处理     │ │  YAML处理            │
│              │ │              │ │                      │
│ 1. 读取全文   │ │ 1. json.load │ │ 1. yaml.safe_load   │
│ 2. 尝试整体   │ │ 2. 判断类型   │ │ 2. 判断类型          │
│    json.loads │ │   - dict     │ │   - dict → [dict]   │
│ 3. 失败则逐行 │ │     → [dict] │ │   - list → list     │
│    解析       │ │   - list     │ │                      │
│              │ │     → list   │ │                      │
└──────┬───────┘ └──────┬───────┘ └──────┬───────────────┘
       │                │                │
       └────────────────┴────────────────┘
                        │
                        ↓
┌─────────────────────────────────────────────────────────────┐
│         返回: List[Dict[str, Any]]                          │
│         blueprints = [                                      │
│           {"name": "Agent1", "tools": [...], ...},          │
│           {"name": "Agent2", "tools": [...], ...},          │
│           ...                                               │
│         ]                                                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 4: 处理entry_agent_name                         │
│         如果配置了entry_agent_name:                           │
│           将指定的Agent移到列表第一位                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 5: 加载工具                                      │
│         tools = load_tools(config)                          │
│         tool_map = {tool.name: tool, ...}                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 6: 为每个blueprint选择工具                       │
│         对于每个blueprint:                                    │
│           if blueprint["tools"]:                            │
│             使用指定工具                                       │
│           elif fill_with_all_tools:                         │
│             使用所有工具                                       │
│           else:                                             │
│             不分配工具                                        │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 7: 创建Agent实例                                │
│         primary_agent = Agent(                              │
│           tools=selected_tools,                             │
│           model=model,                                      │
│           **blueprint_params                                │
│         )                                                   │
│                                                             │
│         managed_agents = [Agent(...), ...]                  │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│         Step 8: 返回AgentBundle                              │
│         包含:                                                 │
│           - primary agent                                   │
│           - managed agents                                  │
│           - blueprints                                      │
│           - tool_map                                        │
│           - model                                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────────────────────┐
│                  完成: Agent已就绪                            │
└─────────────────────────────────────────────────────────────┘
```

---

## _load_blueprints_from_file 详细流程

```
                    _load_blueprints_from_file(path)
                                │
                                ↓
                    ┌───────────────────────┐
                    │  检查文件扩展名          │
                    │  path.suffix.lower()  │
                    └───────┬───────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ↓ .jsonl            ↓ .json             ↓ .yaml/.yml
┌───────────────────┐ ┌──────────────┐ ┌──────────────────┐
│  JSONL特殊处理      │ │  JSON标准处理  │ │  YAML标准处理      │
└───────┬───────────┘ └──────┬───────┘ └──────┬───────────┘
        │                    │                │
        ↓                    ↓                ↓
┌────────────────────────────────────────────────────────┐
│  JSONL: 尝试两种格式                                      │
│                                                         │
│  1. 整体解析:                                            │
│     content = file.read()                              │
│     try:                                               │
│       data = json.loads(content)  # 单个对象             │
│       return [data]                                    │
│                                                         │
│  2. 逐行解析:                                            │
│     except JSONDecodeError:                            │
│       blueprints = []                                  │
│       for line in file:                                │
│         if line.strip():                               │
│           blueprints.append(json.loads(line))          │
│       return blueprints                                │
└────────────────────────────────────────────────────────┘
        │
        ↓
┌────────────────────────────────────────────────────────┐
│  JSON/YAML: 统一处理                                      │
│                                                         │
│  data = json.load(f)  # 或 yaml.safe_load(f)           │
│                                                         │
│  if isinstance(data, list):                            │
│    return [item for item in data if isinstance(item, dict)]│
│  elif isinstance(data, dict):                          │
│    return [data]                                       │
│  else:                                                 │
│    warning + return []                                 │
└────────────────────────────────────────────────────────┘
        │
        ↓
┌────────────────────────────────────────────────────────┐
│  返回: List[Dict[str, Any]]                             │
│                                                         │
│  成功: [{"name": "...", ...}, ...]                      │
│  失败: [] (空列表 + 警告信息)                             │
└────────────────────────────────────────────────────────┘
```

---

## 文件格式判断流程

```
                        文件路径: path
                              │
                              ↓
                    ┌─────────────────────┐
                    │  获取扩展名           │
                    │  ext = path.suffix   │
                    │  .lower()            │
                    └──────────┬──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ↓                     ↓                     ↓
    .jsonl                 .json              .yaml / .yml
        │                     │                     │
        ↓                     ↓                     ↓
┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│ JSON Lines格式  │  │ JSON格式          │  │ YAML格式         │
│                │  │                  │  │                 │
│ 每行一个JSON    │  │ 单个对象或数组     │  │ 单个对象或列表   │
└────────────────┘  └──────────────────┘  └─────────────────┘
        │                     │                     │
        ↓                     ↓                     ↓
┌────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│ 示例:           │  │ 示例:             │  │ 示例:            │
│ {"name":"A"}   │  │ {                │  │ name: Agent     │
│ {"name":"B"}   │  │   "name": "A"    │  │ tools:          │
│ {"name":"C"}   │  │ }                │  │   - tool1       │
│                │  │ 或               │  │   - tool2       │
│                │  │ [                │  │ 或              │
│                │  │   {"name":"A"},  │  │ - name: A       │
│                │  │   {"name":"B"}   │  │ - name: B       │
│                │  │ ]                │  │                 │
└────────────────┘  └──────────────────┘  └─────────────────┘
```

---

## Blueprint数据结构

```
┌────────────────────────────────────────────────────────────────┐
│  Blueprint: Dict[str, Any]                                     │
│  (Agent定义字典)                                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  必需字段:                                                       │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ "name": str            # Agent名称                    │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  常用字段:                                                       │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ "description": str     # Agent描述                    │     │
│  │ "agent_type": str      # "ToolCallingAgent" / "CodeAgent" │ │
│  │ "tools": List[str]     # ["tool1", "tool2"]          │     │
│  │ "system_prompt": str   # 系统提示                     │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  配置字段:                                                       │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ "max_steps": int       # 最大步数                     │     │
│  │ "planning_interval": int # 规划间隔                   │     │
│  │ "stream_outputs": bool # 流式输出                     │     │
│  │ "max_tool_threads": int # 工具并行数                  │     │
│  │ "verbosity_level": int # 日志级别                     │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  多Agent字段:                                                    │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ "node": List[str]      # 子Agent列表                  │     │
│  │                        # ["Agent1", "Agent2"]         │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
│  CodeAgent专有:                                                 │
│  ┌──────────────────────────────────────────────────────┐     │
│  │ "additional_authorized_imports": List[str]           │     │
│  │ "executor_type": str                                 │     │
│  └──────────────────────────────────────────────────────┘     │
│                                                                │
└────────────────────────────────────────────────────────────────┘

示例Blueprint对象:
{
  "name": "DatabaseAgent",
  "description": "SQL expert",
  "agent_type": "ToolCallingAgent",
  "tools": ["execute_sql", "describe_table"],
  "system_prompt": "You are a database expert...",
  "max_steps": 20,
  "planning_interval": 3,
  "stream_outputs": true,
  "verbosity_level": 2
}
```

---

## 多Agent加载示例

```
文件: multi_agents.jsonl
┌──────────────────────────────────────────────────────┐
│ {"name": "Manager", "node": ["W1", "W2"]}           │ ← 第1行
│ {"name": "W1", "tools": ["task1"]}                  │ ← 第2行
│ {"name": "W2", "tools": ["task2"]}                  │ ← 第3行
└──────────────────────────────────────────────────────┘
                    │
                    ↓ _load_blueprints_from_file
┌──────────────────────────────────────────────────────┐
│ blueprints = [                                       │
│   {"name": "Manager", "node": ["W1", "W2"]},        │ ← index 0
│   {"name": "W1", "tools": ["task1"]},               │ ← index 1
│   {"name": "W2", "tools": ["task2"]}                │ ← index 2
│ ]                                                    │
└──────────────────┬───────────────────────────────────┘
                   │
                   ↓ 如果配置了 entry_agent_name="Manager"
┌──────────────────────────────────────────────────────┐
│ _prioritize_blueprints(blueprints, "Manager")       │
│                                                      │
│ Manager已在第一位，无需移动                            │
└──────────────────┬───────────────────────────────────┘
                   │
                   ↓ 创建Agent实例
┌──────────────────────────────────────────────────────┐
│ Primary Agent: Manager                               │
│   - 管理 W1 和 W2                                     │
│   - 可以调用它们完成任务                               │
│                                                      │
│ Managed Agents: [W1, W2]                            │
│   - W1: 使用 task1 工具                              │
│   - W2: 使用 task2 工具                              │
└──────────────────────────────────────────────────────┘
                   │
                   ↓
           ┌────────────────────┐
           │  Agent层级结构:     │
           │                    │
           │     Manager        │
           │     ├─ W1          │
           │     └─ W2          │
           └────────────────────┘
```

---

## 错误处理流程

```
                _load_blueprints_from_file(path)
                            │
                            ↓
                ┌───────────────────┐
                │  path.exists()?   │
                └────┬──────────┬───┘
                     │ 否        │ 是
                     ↓          ↓
            ┌────────────┐  ┌──────────────┐
            │ 返回 []     │  │  继续处理      │
            │ 打印警告    │  └──────┬───────┘
            └────────────┘          │
                                   ↓
                        ┌──────────────────┐
                        │  try: 解析文件    │
                        └────┬──────────┬──┘
                             │ 成功      │ 失败
                             ↓          ↓
                    ┌────────────┐  ┌──────────────────┐
                    │ 返回结果    │  │ except Exception: │
                    │ List[Dict] │  │   打印警告         │
                    └────────────┘  │   return []       │
                                   └──────────────────┘

常见错误:
1. FileNotFoundError    → 返回 []，警告: 文件不存在
2. JSONDecodeError      → 返回 []，警告: JSON格式错误
3. YAMLError            → 返回 []，警告: YAML格式错误
4. PermissionError      → 返回 []，警告: 文件无读取权限
```

---

## 工具选择流程

```
           对于每个Blueprint中的tools字段
                       │
                       ↓
        ┌──────────────────────────────┐
        │  blueprint.get("tools")      │
        └──────┬───────────────────────┘
               │
    ┌──────────┴──────────┐
    │ 有                   │ 无/None/[]
    ↓                     ↓
┌─────────────────┐  ┌──────────────────────┐
│ 使用指定的工具    │  │ fill_with_all_tools? │
│                 │  └────┬────────────┬────┘
│ tools_list =    │       │ true       │ false
│ [tool_map[name] │       ↓            ↓
│  for name       │  ┌─────────┐  ┌─────────┐
│  in tools       │  │ 所有工具  │  │ 空列表   │
│  if found]      │  └─────────┘  └─────────┘
└─────────────────┘
        │
        ↓
┌──────────────────────────────────┐
│  检查每个工具名                    │
│                                  │
│  for tool_name in requested:     │
│    if tool_name in tool_map:     │
│      selected.append(tool)       │
│    else:                         │
│      warning(tool not found)     │
└──────────────────┬───────────────┘
                   │
                   ↓
           ┌───────────────┐
           │  selected为空?  │
           └───┬───────┬───┘
               │ 否     │ 是
               ↓       ↓
          ┌────┐  ┌───────────────────┐
          │返回 │  │ fill_with_all_tools?│
          └────┘  └───┬───────────┬───┘
                      │ true      │ false
                      ↓           ↓
                 ┌─────────┐  ┌────────┐
                 │所有工具  │  │ 空列表  │
                 │(fallback)│  └────────┘
                 └─────────┘

示例:
1. {"tools": ["tool1", "tool2"]}     → [Tool1, Tool2]
2. {"tools": []}                     → depends on fill_with_all_tools
3. {} (无tools字段)                   → depends on fill_with_all_tools
4. {"tools": ["missing"]}            → warning + fallback
```

---

## 实际调用示例

### 场景1: 单个JSON文件

```python
# 1. 文件内容
# agent.json:
{
  "name": "Agent",
  "tools": ["tool1"]
}

# 2. 调用
blueprints = _load_blueprints_from_file(Path("agent.json"))

# 3. 返回
[{"name": "Agent", "tools": ["tool1"]}]

# 4. 使用
primary_bp = blueprints[0]
agent = ToolCallingAgent(
    name=primary_bp["name"],
    tools=get_tools(primary_bp["tools"]),
    model=model
)
```

### 场景2: JSONL多个Agent

```python
# 1. 文件内容
# agents.jsonl:
{"name": "A", "tools": ["t1"]}
{"name": "B", "tools": ["t2"]}

# 2. 调用
blueprints = _load_blueprints_from_file(Path("agents.jsonl"))

# 3. 返回
[
  {"name": "A", "tools": ["t1"]},
  {"name": "B", "tools": ["t2"]}
]

# 4. 使用
primary = create_agent(blueprints[0])  # Agent A
managed = [create_agent(bp) for bp in blueprints[1:]]  # Agent B
primary.managed_agents = managed
```

### 场景3: YAML配置

```python
# 1. 文件内容
# agent.yaml:
name: Agent
tools:
  - tool1
  - tool2
max_steps: 30

# 2. 调用
blueprints = _load_blueprints_from_file(Path("agent.yaml"))

# 3. 返回
[{
  "name": "Agent",
  "tools": ["tool1", "tool2"],
  "max_steps": 30
}]

# 4. 使用
bp = blueprints[0]
agent = ToolCallingAgent(
    name=bp["name"],
    tools=get_tools(bp["tools"]),
    max_steps=bp["max_steps"],
    model=model
)
```

---

**说明**: 本流程图展示了从配置文件到Agent实例化的完整过程，重点展示了 `_load_blueprints_from_file` 函数在其中的核心作用。
