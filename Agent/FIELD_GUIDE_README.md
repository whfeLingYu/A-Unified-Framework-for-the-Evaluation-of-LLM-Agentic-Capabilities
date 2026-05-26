# Agent配置字段完整指南

本目录提供Agent配置的完整参考文档和示例文件。

## 📚 文档结构

### 1. 模板文件

#### `AGENT_CONFIG_TEMPLATE.jsonc`
- **用途**: 带详细注释的完整Agent配置模板
- **格式**: JSONC (JSON with Comments)
- **内容**: 包含所有可配置字段及其详细说明
- **使用方法**:
  - 在支持JSONC的编辑器中直接查看和编辑（VS Code、WebStorm等）
  - 复制需要的字段到您的配置文件
  - 删除注释后可转为标准JSON使用

#### `FIELD_REFERENCE.md`
- **用途**: 完整的字段参考手册
- **格式**: Markdown文档
- **内容**: 每个字段的详细说明表格
- **特点**:
  - 按类别组织（必需字段、基础配置、工具配置等）
  - 包含字段类型、默认值、示例
  - 提供使用建议和注意事项
  - 包含完整的使用示例

### 2. 实用示例文件

#### `examples/08_complete_toolcalling_agent.json`
- **类型**: ToolCallingAgent完整配置
- **特点**:
  - 标准JSON格式，可直接使用
  - 包含所有常用字段
  - 适用于大多数工具调用场景
- **使用场景**:
  - 需要调用预定义工具的任务
  - 一般性的问答和任务执行
  - 多步骤推理任务

#### `examples/09_complete_code_agent.json`
- **类型**: CodeAgent完整配置
- **特点**:
  - 标准JSON格式，可直接使用
  - 包含CodeAgent专用字段
  - 预配置常用Python库
- **使用场景**:
  - 数据分析任务
  - 科学计算
  - 数据可视化
  - 需要执行Python代码的场景

---

## 🚀 快速开始

### 方法1: 从模板开始

1. **查看带注释的模板**
```bash
# 在VS Code或其他支持JSONC的编辑器中打开
code Agent/AGENT_CONFIG_TEMPLATE.jsonc
```

2. **复制需要的字段**
```json
{
  "name": "MyAgent",
  "description": "我的Agent描述",
  "agent_type": "ToolCallingAgent",
  "tools": ["tool1", "tool2"],
  "max_steps": 20
}
```

3. **保存为标准JSON**
```bash
# 删除所有注释后保存
Agent/my_agent.json
```

### 方法2: 从完整示例开始

1. **复制完整示例**
```bash
# ToolCallingAgent
cp Agent/examples/08_complete_toolcalling_agent.json Agent/my_agent.json

# 或 CodeAgent
cp Agent/examples/09_complete_code_agent.json Agent/my_agent.json
```

2. **修改配置**
```bash
# 编辑文件，修改name、tools、system_prompt等字段
vim Agent/my_agent.json
```

3. **在配置文件中引用**
```yaml
# config.yaml
Agent:
  type: single-agent
  agent_dir: ./Agent/my_agent.json
```

### 方法3: 查阅字段手册

1. **打开字段参考手册**
```bash
# 在Markdown查看器或浏览器中打开
open Agent/FIELD_REFERENCE.md
```

2. **查找需要的字段**
- 使用目录快速定位
- 查看字段说明表格
- 复制示例代码

3. **构建自己的配置**
```json
{
  "name": "CustomAgent",
  "description": "根据手册构建的自定义Agent",
  "agent_type": "ToolCallingAgent",
  "tools": ["tool1", "tool2"],
  "max_steps": 25,
  "planning_interval": 5,
  "verbosity_level": 1
}
```

---

## 📖 使用场景指南

### 场景1: 创建简单的工具调用Agent

**需求**: 创建一个能搜索网页和读取文件的Agent

**步骤**:
1. 从`08_complete_toolcalling_agent.json`复制
2. 修改`name`为`"WebSearchAgent"`
3. 修改`tools`为`["search_web", "read_file"]`
4. 调整`system_prompt`描述Agent的角色

**结果**:
```json
{
  "name": "WebSearchAgent",
  "description": "Agent that can search the web and read files",
  "agent_type": "ToolCallingAgent",
  "system_prompt": "You are a research assistant that helps users find information online.",
  "tools": ["search_web", "read_file"],
  "max_steps": 20,
  "verbosity_level": 1
}
```

### 场景2: 创建数据分析Agent

**需求**: 创建一个能分析CSV文件的Python Agent

**步骤**:
1. 从`09_complete_code_agent.json`复制
2. 修改`name`为`"CSVAnalyzer"`
3. 确保`additional_authorized_imports`包含`pandas`, `numpy`
4. 设置合适的`code_execution_timeout`

**结果**:
```json
{
  "name": "CSVAnalyzer",
  "description": "Analyzes CSV files using Python",
  "agent_type": "CodeAgent",
  "system_prompt": "You are a data analyst expert. Analyze CSV files and provide insights.",
  "tools": ["load_csv", "save_file"],
  "additional_authorized_imports": ["pandas", "numpy", "matplotlib"],
  "max_steps": 30,
  "code_execution_timeout": 60
}
```

### 场景3: 创建多Agent协作系统

**需求**: 创建一个管理者和两个工作者的层级结构

**步骤**:
1. 创建JSONL文件（每行一个Agent）
2. 第一个Agent设置`node`字段引用子Agent
3. 子Agent配置各自的工具

**结果**:
```json
{"name": "Manager", "description": "Coordinates tasks", "node": ["Worker1", "Worker2"], "tools": ["assign_task"], "max_steps": 15}
{"name": "Worker1", "description": "Handles search tasks", "tools": ["search_web", "read_file"], "max_steps": 20}
{"name": "Worker2", "description": "Handles analysis tasks", "tools": ["analyze_data", "create_chart"], "max_steps": 20}
```

---

## 🔍 字段查找表

### 按功能分类

| 功能 | 相关字段 | 参考文档 |
|------|---------|---------|
| **基本身份** | `name`, `description`, `agent_type` | FIELD_REFERENCE.md §1-2 |
| **行为定义** | `system_prompt`, `instructions` | FIELD_REFERENCE.md §2 |
| **工具使用** | `tools` | FIELD_REFERENCE.md §3 |
| **执行控制** | `max_steps`, `planning_interval`, `max_tool_threads` | FIELD_REFERENCE.md §4 |
| **输出控制** | `stream_outputs`, `verbosity_level`, `provide_final_answer_only` | FIELD_REFERENCE.md §5 |
| **多Agent** | `node` | FIELD_REFERENCE.md §6 |
| **代码执行** | `additional_authorized_imports`, `max_iterations`, `code_execution_timeout` | FIELD_REFERENCE.md §7 |
| **高级配置** | `prompt_templates`, `temperature`, `memory_bank_size` | FIELD_REFERENCE.md §8 |

### 按Agent类型

| Agent类型 | 必需字段 | 推荐字段 | 专用字段 |
|----------|---------|---------|---------|
| **ToolCallingAgent** | `name` | `description`, `tools`, `system_prompt`, `max_steps` | 无 |
| **CodeAgent** | `name`, `agent_type: "CodeAgent"` | `additional_authorized_imports`, `max_steps` | `additional_authorized_imports`, `max_iterations`, `code_execution_timeout` |

---

## 🐛 常见问题

### Q1: JSON文件中可以添加注释吗？

**A**: 标准JSON不支持注释。解决方案：
- 使用JSONC格式（`.jsonc`扩展名）在编辑器中查看
- 或者使用YAML格式（`.yaml`扩展名），原生支持注释
- 实际部署时必须删除所有注释

### Q2: 如何知道某个字段是否必需？

**A**: 查看`FIELD_REFERENCE.md`中的字段表格：
- ✅ **必需: 是** - 必须提供
- ❌ **必需: 否** - 可选字段

目前唯一必需的字段是`name`。

### Q3: tools字段设为null和不设置有什么区别？

**A**: 没有区别。两种情况下：
- 如果配置中`fill_with_all_tools: true` → Agent获得所有工具
- 如果配置中`fill_with_all_tools: false` → Agent没有工具

### Q4: 如何使用外部文件作为system_prompt？

**A**: 将`system_prompt`设为文件路径：
```json
{
  "name": "Agent",
  "system_prompt": "./Agent/prompts/my_prompt.txt"
}
```
框架会自动读取文件内容。

### Q5: CodeAgent和ToolCallingAgent可以混用吗？

**A**: 可以！在多Agent场景中：
```json
[
  {"name": "Coordinator", "agent_type": "ToolCallingAgent", "tools": ["delegate"]},
  {"name": "Analyst", "agent_type": "CodeAgent", "additional_authorized_imports": ["pandas"]}
]
```

### Q6: 如何调试Agent配置？

**A**:
1. 设置`verbosity_level: 2`查看详细日志
2. 使用`python main.py --verbose`运行
3. 检查日志中的Agent加载信息
4. 验证tools列表中的工具都存在

---

## 📝 配置检查清单

在部署Agent之前，检查以下项目：

- [ ] **必需字段**: `name`已设置且唯一
- [ ] **Agent类型**: `agent_type`正确（ToolCallingAgent或CodeAgent）
- [ ] **工具配置**: `tools`列表中的工具在Toolkit中存在
- [ ] **系统提示**: `system_prompt`或`description`已设置
- [ ] **文件路径**: 如果使用文件路径，确保文件存在
- [ ] **多Agent**: 如果使用`node`，确保引用的Agent存在
- [ ] **CodeAgent**: 如果使用CodeAgent，确保所需库已安装
- [ ] **JSON语法**: 使用jsonlint验证JSON语法正确
- [ ] **字段拼写**: 确保字段名称拼写正确（区分大小写）

---

## 🔗 相关资源

### 文档导航

```
Agent/
├── AGENT_CONFIG_TEMPLATE.jsonc          # 👈 带注释的完整模板
├── FIELD_REFERENCE.md                   # 👈 字段参考手册（本文档推荐）
├── FIELD_GUIDE_README.md                # 👈 使用指南（当前文档）
├── AGENT_DEFINITION_GUIDE.md            # 详细定义指南
├── BLUEPRINT_LOADING_GUIDE.md           # 加载机制详解
├── LOADING_FLOWCHART.md                 # 加载流程图
├── QUICK_REFERENCE.md                   # 快速参考卡
├── test_blueprint_loading.py            # 测试脚本
└── examples/
    ├── 01_minimal_agent.jsonl           # 最小配置
    ├── 02_complete_single_agent.jsonl   # 完整单Agent
    ├── 03_code_agent.jsonl              # CodeAgent
    ├── 04_multi_agent_parallel.jsonl    # 并行多Agent
    ├── 05_multi_agent_hierarchy.jsonl   # 层级多Agent
    ├── 06_agent_with_prompt_file.jsonl  # 外部提示文件
    ├── 07_agent_with_templates.yaml     # YAML格式
    ├── 08_complete_toolcalling_agent.json  # 👈 完整ToolCallingAgent
    ├── 09_complete_code_agent.json         # 👈 完整CodeAgent
    └── README.md                        # 示例说明
```

### 推荐阅读顺序

1. **快速入门**: `QUICK_REFERENCE.md`
2. **字段详解**: `FIELD_REFERENCE.md`（本文档）
3. **使用示例**: `examples/README.md`
4. **加载机制**: `BLUEPRINT_LOADING_GUIDE.md`
5. **完整指南**: `AGENT_DEFINITION_GUIDE.md`

---

## 💡 最佳实践

### 1. 从简单开始
```json
{
  "name": "MyAgent",
  "description": "Simple agent",
  "tools": ["tool1", "tool2"]
}
```

### 2. 逐步添加配置
```json
{
  "name": "MyAgent",
  "description": "Enhanced agent",
  "tools": ["tool1", "tool2"],
  "max_steps": 20,              // 添加步数限制
  "verbosity_level": 1          // 添加日志控制
}
```

### 3. 针对性能优化
```json
{
  "name": "MyAgent",
  "description": "Optimized agent",
  "tools": ["tool1", "tool2"],
  "max_steps": 20,
  "planning_interval": 5,       // 添加规划
  "max_tool_threads": 2         // 并行执行
}
```

### 4. 生产环境配置
```json
{
  "name": "ProductionAgent",
  "description": "Production-ready agent",
  "system_prompt": "./prompts/production_prompt.txt",
  "tools": ["tool1", "tool2"],
  "max_steps": 30,
  "planning_interval": 5,
  "verbosity_level": 1,
  "provide_run_summary": true,
  "metadata": {
    "version": "1.0",
    "environment": "production",
    "last_tested": "2024-01-28"
  }
}
```

---

**最后更新**: 2024-01-28
**维护者**: Framework Team

如有问题或建议，请查阅相关文档或联系开发团队。
