# Agent Definition Quick Reference Card

## 📌 最小化示例

```json
{"name": "Agent", "description": "Helpful assistant"}
```

## 📌 完整单Agent示例

```json
{
  "name": "MyAgent",
  "description": "Agent description",
  "agent_type": "ToolCallingAgent",
  "system_prompt": "You are a helpful assistant...",
  "tools": ["tool1", "tool2"],
  "max_steps": 20,
  "planning_interval": 3,
  "stream_outputs": true,
  "max_tool_threads": 1,
  "verbosity_level": 1
}
```

## 📌 多Agent并行示例

```json lines
{"name": "Manager", "tools": ["delegate"]}
{"name": "Worker1", "tools": ["task1"]}
{"name": "Worker2", "tools": ["task2"]}
```

## 📌 多Agent层级示例

```json lines
{"name": "Boss", "node": ["Manager"]}
{"name": "Manager", "node": ["Worker1", "Worker2"]}
{"name": "Worker1", "tools": ["task1"]}
{"name": "Worker2", "tools": ["task2"]}
```

---

## 🔑 必需字段

| 字段 | 说明 |
|------|------|
| `name` | Agent名称 |

## ⭐ 常用字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `description` | string | - | Agent描述（后备system_prompt）|
| `agent_type` | string | ToolCallingAgent | Agent类型 |
| `tools` | array | null | 工具名称列表 |
| `system_prompt` | string/path | - | 系统提示 |
| `max_steps` | int | 20 | 最大步数 |
| `planning_interval` | int | null | 规划间隔 |

## 🎯 Agent类型

| 类型 | 说明 | 使用场景 |
|------|------|----------|
| `ToolCallingAgent` | 调用预定义工具 | 大多数场景（推荐）|
| `CodeAgent` | 生成执行Python代码 | 数据分析、计算 |

## 📝 System Prompt优先级

1. `instructions` 字段
2. `system_prompt` 字段
3. `description` 字段
4. 配置文件中的全局设置

## 🔧 工具选择逻辑

```python
if blueprint["tools"]:
    # 使用指定工具
    use_these_tools
elif fill_with_all_tools:
    # 使用所有工具
    use_all_tools
else:
    # 不分配工具
    no_tools
```

## 🏗️ 配置示例

### 单Agent配置
```yaml
Agent:
  type: single-agent
  agent_dir: ./Agent/my_agent.jsonl
  agent_type: ToolCallingAgent
  fill_with_all_tools: true
```

### 多Agent配置
```yaml
Agent:
  type: multi-agent
  agent_dir: ./Agent/multi_agents.jsonl
  entry_agent_name: Manager
  fill_with_all_tools: false
```

## 📂 文件格式支持

| 格式 | 扩展名 | 用法 |
|------|--------|------|
| JSON | `.json` | 单个对象或数组 |
| JSON Lines | `.jsonl` | 每行一个Agent |
| YAML | `.yaml`, `.yml` | 单个对象或数组 |

## 🔍 加载机制

1. 读取 `agent_dir` 指定的文件/目录
2. 解析Agent定义（JSON/JSONL/YAML）
3. 如果指定 `entry_agent_name`，该Agent成为primary
4. 否则第一个Agent成为primary
5. 其余Agent成为managed agents

## ⚡ 常见模式

### 模式1：最简配置
```json
{"name": "Agent"}
```
配合 `fill_with_all_tools: true`

### 模式2：明确工具
```json
{"name": "Agent", "tools": ["tool1", "tool2"]}
```
只使用指定工具

### 模式3：外部提示
```json
{"name": "Agent", "system_prompt": "./prompts/agent.txt"}
```
从文件加载提示

### 模式4：完整配置
```json
{
  "name": "Agent",
  "description": "...",
  "system_prompt": "...",
  "tools": [...],
  "max_steps": 20,
  "prompt_templates": "./templates.yaml"
}
```

## 🐛 调试清单

- [ ] 检查JSON语法（使用 jsonlint）
- [ ] 确认 `agent_dir` 路径正确
- [ ] 验证 `tools` 列表中的工具存在
- [ ] 检查 `system_prompt` 文件路径（如果是路径）
- [ ] 确认 `node` 引用的Agent存在（多Agent）
- [ ] 查看日志中的Agent加载信息
- [ ] 设置 `verbosity_level: 2` 查看详细日志

## 📚 参考资源

- **详细指南**: [AGENT_DEFINITION_GUIDE.md](./AGENT_DEFINITION_GUIDE.md)
- **示例文件**: [examples/](./examples/)
- **配置指南**: [../Config/CONFIG_GUIDE_CN.md](../Config/CONFIG_GUIDE_CN.md)

---

**提示**: 从示例开始，逐步添加配置！
