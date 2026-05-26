# Agent配置字段完整参考手册

本文档详细说明Agent配置JSON/JSONL/YAML文件中每个字段的含义、类型、默认值和使用方法。

## 📑 目录

1. [必需字段](#必需字段)
2. [基础配置字段](#基础配置字段)
3. [工具配置字段](#工具配置字段)
4. [执行控制字段](#执行控制字段)
5. [输出控制字段](#输出控制字段)
6. [多Agent配置字段](#多agent配置字段)
7. [CodeAgent专用字段](#codeagent专用字段)
8. [高级配置字段](#高级配置字段)
9. [字段优先级规则](#字段优先级规则)
10. [完整示例](#完整示例)

---

## 必需字段

### `name`

| 属性 | 值 |
|------|-----|
| **说明** | Agent的唯一标识名称 |
| **类型** | `string` |
| **必需** | ✅ 是 |
| **默认值** | 无（必须提供） |
| **示例** | `"DatabaseExpert"`, `"DataAnalyst"`, `"ResearchAssistant"` |
| **注意事项** | • 在多Agent场景中，name用于agent之间的引用和调用<br>• 名称必须唯一，不能重复<br>• 建议使用有意义的描述性名称 |

**示例**：
```json
{
  "name": "DatabaseExpert"
}
```

---

## 基础配置字段

### `description`

| 属性 | 值 |
|------|-----|
| **说明** | Agent的功能描述 |
| **类型** | `string` |
| **必需** | ❌ 否 |
| **默认值** | `""` (空字符串) |
| **示例** | `"Expert database query assistant with SQL expertise"` |
| **注意事项** | • 当没有`system_prompt`时会作为默认系统提示<br>• 优先级低于`system_prompt`和`instructions`<br>• 建议简洁明了地描述Agent的主要功能 |

**示例**：
```json
{
  "name": "DatabaseExpert",
  "description": "Expert at writing and optimizing SQL queries for complex database operations"
}
```

---

### `agent_type`

| 属性 | 值 |
|------|-----|
| **说明** | Agent的类型，决定Agent的行为模式 |
| **类型** | `string` |
| **必需** | ❌ 否 |
| **默认值** | `"ToolCallingAgent"` |
| **可选值** | `"ToolCallingAgent"` \| `"CodeAgent"` |
| **注意事项** | • `ToolCallingAgent`: 调用预定义工具（推荐，适用于大多数场景）<br>• `CodeAgent`: 生成并执行Python代码（适用于数据分析、计算等）<br>• 不同类型支持的配置字段略有不同 |

**ToolCallingAgent示例**：
```json
{
  "name": "TaskAgent",
  "agent_type": "ToolCallingAgent",
  "tools": ["search_web", "read_file"]
}
```

**CodeAgent示例**：
```json
{
  "name": "DataAnalyst",
  "agent_type": "CodeAgent",
  "additional_authorized_imports": ["numpy", "pandas"]
}
```

---

### `system_prompt`

| 属性 | 值 |
|------|-----|
| **说明** | Agent的系统提示词，定义Agent的行为、角色和能力 |
| **类型** | `string` (直接文本) 或 `path` (文件路径) |
| **必需** | ❌ 否 |
| **默认值** | 使用`description`或配置文件中的全局设置 |
| **注意事项** | • 优先级高于`description`字段<br>• 支持文件路径（框架会自动读取文件内容）<br>• 文件路径识别：以`.txt`, `.md`结尾<br>• 支持多行文本 |

**直接文本示例**：
```json
{
  "name": "SQLExpert",
  "system_prompt": "You are an expert database administrator with 10+ years of experience. You excel at writing optimized SQL queries and explaining complex database concepts."
}
```

**文件路径示例**：
```json
{
  "name": "SupportAgent",
  "system_prompt": "./Agent/prompts/customer_support_prompt.txt"
}
```

---

### `instructions`

| 属性 | 值 |
|------|-----|
| **说明** | Agent的指令，最高优先级的系统提示 |
| **类型** | `string` 或 `null` |
| **必需** | ❌ 否 |
| **默认值** | `null` |
| **注意事项** | • 优先级最高，会覆盖`system_prompt`和`description`<br>• 通常用于临时覆盖系统提示 |

**示例**：
```json
{
  "name": "Agent",
  "instructions": "Focus only on providing concise answers without explanations."
}
```

---

## 工具配置字段

### `tools`

| 属性 | 值 |
|------|-----|
| **说明** | Agent可以使用的工具列表 |
| **类型** | `array of strings` 或 `null` |
| **必需** | ❌ 否 |
| **默认值** | `null` |
| **示例** | `["execute_sql", "describe_table", "show_tables"]` |
| **注意事项** | • 工具名称必须在Toolkit中定义<br>• `null`时的行为取决于配置中的`fill_with_all_tools`设置 |

**工具选择逻辑**：
```
if tools列表存在:
    使用指定的工具
elif fill_with_all_tools = true:
    使用所有可用工具
else:
    不分配任何工具
```

**示例**：
```json
{
  "name": "DatabaseExpert",
  "tools": [
    "execute_sql",
    "describe_table",
    "show_tables",
    "show_columns",
    "get_table_schema"
  ]
}
```

---

## 执行控制字段

### `max_steps`

| 属性 | 值 |
|------|-----|
| **说明** | Agent执行的最大步数限制 |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `20` |
| **范围** | 1-100（建议） |
| **注意事项** | • 超过此步数Agent将停止执行<br>• 根据任务复杂度调整 |

**推荐值**：
- 简单任务：10-15
- 中等任务：20-30
- 复杂任务：40-50

**示例**：
```json
{
  "name": "QuickAgent",
  "max_steps": 10,
  "description": "Fast agent for simple tasks"
}
```

---

### `planning_interval`

| 属性 | 值 |
|------|-----|
| **说明** | Agent进行规划的步数间隔 |
| **类型** | `integer` 或 `null` |
| **必需** | ❌ 否 |
| **默认值** | `null` (不进行规划) |
| **可选值** | `null`: 禁用<br>`-1`: 使用默认<br>`> 0`: 每N步规划一次 |
| **注意事项** | • 规划帮助Agent保持方向<br>• 会增加token消耗<br>• 复杂任务建议启用 |

**示例**：
```json
{
  "name": "PlanningAgent",
  "max_steps": 30,
  "planning_interval": 5,
  "description": "Plans every 5 steps"
}
```

---

### `max_tool_threads`

| 属性 | 值 |
|------|-----|
| **说明** | 工具调用的最大并发线程数 |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `1` |
| **注意事项** | • `1`: 串行执行（安全，推荐）<br>• `>1`: 并行执行（需要工具支持并发）<br>• 某些工具可能不支持并发 |

**示例**：
```json
{
  "name": "FastAgent",
  "max_tool_threads": 4,
  "description": "Agent with parallel tool execution"
}
```

---

## 输出控制字段

### `stream_outputs`

| 属性 | 值 |
|------|-----|
| **说明** | 是否流式输出Agent的响应 |
| **类型** | `boolean` |
| **必需** | ❌ 否 |
| **默认值** | `true` |
| **注意事项** | • `true`: 实时显示Agent的思考和执行过程<br>• `false`: 等待完成后一次性显示 |

---

### `verbosity_level`

| 属性 | 值 |
|------|-----|
| **说明** | 日志详细程度级别 |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `1` |
| **可选值** | `0`: 安静（仅错误）<br>`1`: 正常（常规信息）<br>`2`: 详细（调试信息） |

**示例**：
```json
{
  "name": "DebugAgent",
  "verbosity_level": 2,
  "description": "Agent with verbose logging for debugging"
}
```

---

### `provide_final_answer_only`

| 属性 | 值 |
|------|-----|
| **说明** | 是否仅输出最终答案（隐藏中间过程） |
| **类型** | `boolean` |
| **必需** | ❌ 否 |
| **默认值** | `false` |
| **注意事项** | • `true`: 用户只看到最终结果<br>• `false`: 显示完整执行过程 |

---

### `provide_run_summary`

| 属性 | 值 |
|------|-----|
| **说明** | 是否在执行完成后提供运行摘要 |
| **类型** | `boolean` |
| **必需** | ❌ 否 |
| **默认值** | `true` |
| **注意事项** | 显示执行统计（步数、工具调用次数等） |

---

### `max_output_length`

| 属性 | 值 |
|------|-----|
| **说明** | 单次输出的最大字符数 |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `5000` |
| **推荐值** | 简短任务: 3000<br>默认: 5000<br>长文本: 10000 |

---

## 多Agent配置字段

### `node`

| 属性 | 值 |
|------|-----|
| **说明** | 此Agent的子Agent列表（用于构建层级结构） |
| **类型** | `array of strings` 或 `null` |
| **必需** | ❌ 否（仅多Agent场景需要） |
| **默认值** | `null` |
| **示例** | `["DevLead", "QALead"]` |
| **注意事项** | • 定义Agent的层级关系<br>• 父Agent可以委托任务给子Agent<br>• 引用的Agent名称必须存在 |

**层级结构示例**：
```json
[
  {
    "name": "ProjectManager",
    "node": ["DevLead", "QALead"],
    "tools": ["assign_task", "track_progress"]
  },
  {
    "name": "DevLead",
    "node": ["FrontendDev", "BackendDev"],
    "tools": ["review_code", "merge_pr"]
  },
  {
    "name": "FrontendDev",
    "tools": ["create_component", "style_page"]
  },
  {
    "name": "BackendDev",
    "tools": ["create_api", "setup_database"]
  },
  {
    "name": "QALead",
    "node": ["QAEngineer"],
    "tools": ["create_test_plan"]
  },
  {
    "name": "QAEngineer",
    "tools": ["write_test", "run_tests"]
  }
]
```

**结构可视化**：
```
ProjectManager
├─ DevLead
│  ├─ FrontendDev
│  └─ BackendDev
└─ QALead
   └─ QAEngineer
```

---

## CodeAgent专用字段

### `additional_authorized_imports`

| 属性 | 值 |
|------|-----|
| **说明** | CodeAgent允许导入的额外Python库 |
| **类型** | `array of strings` |
| **必需** | ❌ 否 |
| **默认值** | `[]` |
| **适用** | 仅`agent_type="CodeAgent"`时有效 |
| **示例** | `["numpy", "pandas", "sklearn", "torch"]` |
| **注意事项** | • 确保库在运行环境中已安装<br>• 出于安全考虑，避免危险库（os, sys, subprocess等） |

**示例**：
```json
{
  "name": "DataScientist",
  "agent_type": "CodeAgent",
  "additional_authorized_imports": [
    "numpy",
    "pandas",
    "matplotlib",
    "seaborn",
    "scipy",
    "sklearn"
  ]
}
```

---

### `max_iterations`

| 属性 | 值 |
|------|-----|
| **说明** | CodeAgent代码执行的最大迭代次数 |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `10` |
| **适用** | 仅`agent_type="CodeAgent"`时有效 |

---

### `code_execution_timeout`

| 属性 | 值 |
|------|-----|
| **说明** | 单次代码执行的超时时间（秒） |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `30` |
| **适用** | 仅`agent_type="CodeAgent"`时有效 |

---

## 高级配置字段

### `prompt_templates`

| 属性 | 值 |
|------|-----|
| **说明** | 自定义提示词模板文件路径 |
| **类型** | `string` (文件路径) 或 `null` |
| **必需** | ❌ 否 |
| **默认值** | `null` |
| **示例** | `"./Agent/templates/research_assistant_templates.yaml"` |
| **注意事项** | • 定制Agent在不同阶段使用的提示词<br>• 模板文件必须是有效的YAML格式<br>• 可包含: planning_prompt, tool_calling_prompt等 |

**示例**：
```json
{
  "name": "CustomAgent",
  "prompt_templates": "./Agent/templates/my_templates.yaml"
}
```

---

### `return_intermediate_outputs`

| 属性 | 值 |
|------|-----|
| **说明** | 是否返回中间步骤的输出 |
| **类型** | `boolean` |
| **必需** | ❌ 否 |
| **默认值** | `false` |
| **注意事项** | 用于调试和分析Agent的执行过程 |

---

### `memory_bank_size`

| 属性 | 值 |
|------|-----|
| **说明** | Agent记忆库的大小（存储历史交互） |
| **类型** | `integer` |
| **必需** | ❌ 否 |
| **默认值** | `100` |
| **注意事项** | 较大的记忆库会消耗更多内存 |

---

### `temperature`

| 属性 | 值 |
|------|-----|
| **说明** | 模型生成的温度参数 |
| **类型** | `float` |
| **必需** | ❌ 否 |
| **默认值** | 通常由配置文件中的Model设置决定 |
| **范围** | 0.0-2.0 |
| **推荐值** | 确定性任务: 0.0-0.3<br>平衡: 0.5-0.7<br>创造性: 0.8-1.0 |

---

### `stop_sequences`

| 属性 | 值 |
|------|-----|
| **说明** | 停止序列，遇到这些文本时Agent停止生成 |
| **类型** | `array of strings` |
| **必需** | ❌ 否 |
| **默认值** | `[]` |
| **示例** | `["TASK_COMPLETE", "END"]` |

---

### `metadata`

| 属性 | 值 |
|------|-----|
| **说明** | 自定义元数据，框架不处理 |
| **类型** | `object` |
| **必需** | ❌ 否 |
| **默认值** | `{}` |
| **用途** | 存储版本、作者、标签等信息 |

**示例**：
```json
{
  "name": "Agent",
  "metadata": {
    "version": "1.0",
    "author": "Your Name",
    "tags": ["database", "sql", "expert"],
    "created_at": "2024-01-28",
    "last_modified": "2024-01-28"
  }
}
```

---

## 字段优先级规则

### System Prompt优先级

```
instructions > system_prompt > description > 配置文件全局设置
```

### Tool选择优先级

```
显式tools列表 > fill_with_all_tools设置 > 无工具
```

### 参数覆盖规则

```
Agent定义 > 配置文件Agent section > 框架默认值
```

---

## 完整示例

### 最小配置
```json
{
  "name": "MinimalAgent"
}
```

### 简单配置
```json
{
  "name": "SimpleAgent",
  "description": "A helpful assistant",
  "tools": ["search", "calculator"]
}
```

### 完整ToolCallingAgent
```json
{
  "name": "CompleteAgent",
  "description": "Full-featured tool-calling agent",
  "agent_type": "ToolCallingAgent",
  "system_prompt": "You are an expert assistant...",
  "tools": ["search_web", "read_file", "write_file"],
  "max_steps": 25,
  "planning_interval": 5,
  "max_tool_threads": 1,
  "stream_outputs": true,
  "verbosity_level": 1,
  "provide_final_answer_only": false,
  "provide_run_summary": true,
  "max_output_length": 5000,
  "return_intermediate_outputs": false,
  "memory_bank_size": 100,
  "metadata": {
    "version": "1.0",
    "author": "Team"
  }
}
```

### 完整CodeAgent
```json
{
  "name": "DataAnalystAgent",
  "description": "Python data analysis expert",
  "agent_type": "CodeAgent",
  "system_prompt": "You are an expert Python programmer...",
  "tools": ["load_csv", "save_file"],
  "max_steps": 30,
  "planning_interval": 5,
  "additional_authorized_imports": [
    "numpy",
    "pandas",
    "matplotlib",
    "scipy"
  ],
  "max_iterations": 15,
  "code_execution_timeout": 60,
  "max_output_length": 8000,
  "verbosity_level": 2
}
```

### 多Agent层级
```json
[
  {
    "name": "Manager",
    "description": "Project manager",
    "node": ["Developer", "Tester"],
    "tools": ["assign_task", "track_progress"],
    "max_steps": 20
  },
  {
    "name": "Developer",
    "description": "Software developer",
    "tools": ["write_code", "debug"],
    "max_steps": 30
  },
  {
    "name": "Tester",
    "description": "QA tester",
    "tools": ["run_tests", "report_bug"],
    "max_steps": 15
  }
]
```

---

## 📖 相关文档

- **[AGENT_DEFINITION_GUIDE.md](./AGENT_DEFINITION_GUIDE.md)** - Agent定义完整指南
- **[BLUEPRINT_LOADING_GUIDE.md](./BLUEPRINT_LOADING_GUIDE.md)** - 加载机制详解
- **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** - 快速参考卡
- **[examples/](./examples/)** - 实用示例文件

---

**最后更新**: 2024-01-28
**框架版本**: 1.0+
