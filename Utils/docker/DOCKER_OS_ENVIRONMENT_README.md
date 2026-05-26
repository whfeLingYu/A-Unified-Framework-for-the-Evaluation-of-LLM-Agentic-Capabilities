# Docker OS Environment

真实的 Docker 容器化 OS 环境，用于 Agent 评估和测试。

## 功能特性

- **真实 Linux 环境**: 在 Docker 容器中运行真实的 Linux OS
- **文件系统初始化**: 从 JSON 配置自动创建文件系统结构
- **命令执行**: 支持执行真实的 bash 命令（ls, grep, awk 等）
- **资源隔离**: CPU、内存、网络隔离
- **安全沙箱**: 网络隔离、用户权限控制
- **自动清理**: 容器生命周期自动管理

## 快速开始

### 1. 安装依赖

```bash
pip install docker
```

确保 Docker 已安装并运行：

```bash
docker --version
docker ps  # 测试 Docker 是否正常运行
```

### 2. 构建 Docker 镜像（可选）

如果需要自定义镜像，可以构建：

```bash
cd Environment/Dockerfiles

# 完整版本（包含更多工具）
docker build -t agent-os-env:full -f os_environment.Dockerfile .

# 最小版本（只有基础工具）
docker build -t agent-os-env:minimal -f os_environment_minimal.Dockerfile .
```

也可以直接使用官方镜像：`ubuntu:22.04`

### 3. 基本使用

```python
from Environment.DockerOSEnvironment import DockerOSEnvironment

# 创建环境
config = {
    "image": "ubuntu:22.04",  # 或 "agent-os-env:full"
    "working_dir": "/root",
    "user": "root",
}

# 使用 context manager（推荐）
with DockerOSEnvironment(config) as env:
    # 执行命令
    result = env.execute_command("ls -la /home")
    print(result['stdout'])

    # 写文件
    env.write_file("/tmp/test.txt", "Hello Docker!")

    # 读文件
    content = env.get_file_content("/tmp/test.txt")
    print(content)
```

### 4. 从 AgentBench 任务配置初始化

```python
from Environment.DockerOSEnvironment import DockerOSEnvironmentFactory

# 从 os_task_0.json 创建环境
env = DockerOSEnvironmentFactory.create_from_task_config(
    task_config_path="Environment/AgentBench/os_interaction/os_task_0.json",
    image="ubuntu:22.04"
)

# 现在 JSON 中定义的文件系统是真实的！
result = env.execute_command("cat /usr/stock.log | head -10")
print(result['stdout'])

# 执行任务
result = env.execute_command("grep 'Alice | Sell' /usr/stock.log | wc -l")
print(f"Alice sold stock {result['stdout'].strip()} times")

env.cleanup()
```

## 配置选项

### DockerOSEnvironment 配置

```python
config = {
    # Docker 镜像
    "image": "ubuntu:22.04",

    # 文件系统初始化配置（JSON 文件路径）
    "filesystem_config": "/path/to/os_task.json",

    # 工作目录
    "working_dir": "/root",

    # 执行用户
    "user": "root",  # 或 "alice"

    # 资源限制
    "memory_limit": "512m",  # 内存限制
    "cpu_quota": 50000,      # CPU 限制（50%）

    # 网络模式
    "network_mode": "none",   # 禁用网络（推荐）
    # "network_mode": "bridge",  # 启用网络

    # 容器自动删除
    "auto_remove": False,  # 退出时自动删除容器
}
```

### 文件系统配置格式

JSON 文件格式（如 `os_task_0.json`）：

```json
{
  "filesystem": {
    "home": {
      "type": "directory",
      "children": {
        "alice": {
          "type": "directory",
          "children": {
            "notes.txt": {
              "type": "file",
              "content": "My notes..."
            }
          }
        }
      }
    },
    "usr": {
      "type": "directory",
      "children": {
        "data.log": {
          "type": "file",
          "content": "Log data here..."
        }
      }
    }
  },
  "instruction_text": "Your task description..."
}
```

## API 文档

### DockerOSEnvironment

#### 初始化

```python
env = DockerOSEnvironment(config, logger=None, container_name=None)
env.initialize()
```

#### 执行命令

```python
result = env.execute_command(
    command="ls -la",
    user=None,              # 默认使用 config 中的 user
    working_dir=None,       # 默认使用 config 中的 working_dir
    check=True,             # 失败时是否抛出异常
    capture_output=True,    # 是否捕获输出
    timeout=30              # 超时时间（秒）
)

# 返回值
{
    "exit_code": 0,
    "stdout": "...",
    "stderr": "..."
}
```

#### 文件操作

```python
# 写文件
env.write_file("/path/to/file", "content")

# 读文件
content = env.get_file_content("/path/to/file")

# 列出目录
files = env.list_directory("/path/to/dir")
```

#### 状态查询

```python
state = env.get_current_state()
# 返回：
# {
#     "initialized": True,
#     "container_name": "os-env-123456",
#     "container_id": "abc123",
#     "container_status": "running",
#     "image": "ubuntu:22.04",
#     "user": "root",
#     "working_dir": "/root"
# }
```

#### 清理

```python
env.cleanup()  # 停止并删除容器
```

### DockerOSEnvironmentFactory

#### 从任务配置创建

```python
env = DockerOSEnvironmentFactory.create_from_task_config(
    task_config_path="path/to/task.json",
    image="ubuntu:22.04",
    **kwargs  # 其他配置选项
)
```

#### 创建最小环境

```python
env = DockerOSEnvironmentFactory.create_minimal(
    image="ubuntu:22.04",
    working_dir="/root",
    **kwargs
)
```

## 使用场景

### 场景 1: AgentBench OS Interaction 任务

```python
from Environment.DockerOSEnvironment import DockerOSEnvironmentFactory

# 加载任务
task_path = "Environment/AgentBench/os_interaction/os_task_0.json"
env = DockerOSEnvironmentFactory.create_from_task_config(task_path)

# Agent 执行命令
agent_command = "grep 'Alice | Sell' /usr/stock.log | wc -l"
result = env.execute_command(agent_command)

# 评估结果
answer = result['stdout'].strip()
print(f"Agent answer: {answer}")

env.cleanup()
```

### 场景 2: 批量评估

```python
import json
from pathlib import Path
from Environment.DockerOSEnvironment import DockerOSEnvironmentFactory

task_dir = Path("Environment/AgentBench/os_interaction")
results = []

for task_file in task_dir.glob("os_task_*.json"):
    # 为每个任务创建独立环境
    with DockerOSEnvironmentFactory.create_from_task_config(str(task_file)) as env:
        # 加载任务
        with open(task_file) as f:
            task = json.load(f)

        # Agent 执行（这里简化为示例）
        result = env.execute_command(task['instruction_text'])

        results.append({
            "task": task_file.name,
            "result": result
        })

print(f"Completed {len(results)} tasks")
```

### 场景 3: 安全隔离评估

```python
# 高安全性配置
config = {
    "image": "ubuntu:22.04",
    "network_mode": "none",      # 禁用网络
    "memory_limit": "256m",      # 限制内存
    "cpu_quota": 50000,          # 限制 CPU
    "user": "alice",             # 非 root 用户
    "auto_remove": True,         # 自动清理
}

with DockerOSEnvironment(config) as env:
    # 在隔离环境中运行不受信任的 Agent 代码
    result = env.execute_command("potentially_dangerous_command")
```

## 集成到现有框架

### 修改 runner.py

```python
# 在 Utils/runner.py 中添加 Docker 环境支持

from Environment.DockerOSEnvironment import DockerOSEnvironment

def run_task_with_docker_env(task_config, agent):
    """使用 Docker 环境运行任务"""

    # 创建 Docker 环境
    docker_config = {
        "image": task_config.get("docker_image", "ubuntu:22.04"),
        "filesystem_config": task_config.get("environment_path"),
        "network_mode": "none",
    }

    with DockerOSEnvironment(docker_config) as env:
        # Agent 与环境交互
        for step in range(task_config.get("max_steps", 10)):
            # Agent 生成命令
            command = agent.generate_command(env.get_current_state())

            # 在 Docker 环境中执行
            result = env.execute_command(command, check=False)

            # Agent 观察结果
            agent.observe(result)

            if agent.is_done():
                break

        # 评估结果
        return evaluate_task(task_config, agent, env)
```

### YAML 配置示例

创建 `Config/config_AgentBench/config_os_docker.yaml`:

```yaml
Benchmark:
  type: AgentBench
  domain: os_interaction
  task_path: Benchmark/AgentBench/os_interaction.jsonl

Environment:
  type: docker_os  # 新的环境类型
  config:
    image: ubuntu:22.04
    network_mode: none
    memory_limit: 512m
    cpu_quota: 50000
    user: alice
    auto_remove: true

Agent:
  type: your_agent_type
  model: gpt-4
  max_steps: 20

Evaluation:
  metrics:
    - accuracy
    - success_rate
  output_path: Results/outputs/AgentBench/os_docker/
```

## 安全注意事项

1. **网络隔离**: 默认使用 `network_mode: "none"` 禁用网络
2. **资源限制**: 设置内存和 CPU 限制防止资源耗尽
3. **非 root 用户**: 尽可能使用非 root 用户运行命令
4. **自动清理**: 使用 context manager 或设置 `auto_remove: True`
5. **只读挂载**: 如需挂载主机目录，使用只读模式

## 故障排查

### Docker 连接失败

```
RuntimeError: Failed to connect to Docker daemon
```

解决方案：
- 确保 Docker Desktop/Engine 正在运行
- 检查 Docker 权限：`docker ps`
- Mac/Linux: 确保用户在 docker 组中

### 镜像拉取失败

```
ImageNotFound: ubuntu:22.04
```

解决方案：
- 手动拉取镜像：`docker pull ubuntu:22.04`
- 检查网络连接
- 使用国内镜像源（如有需要）

### 容器启动失败

```
Container failed to start
```

解决方案：
- 检查资源限制是否过低
- 查看容器日志：`docker logs <container_name>`
- 降低资源限制或增加超时时间

### 权限问题

```
Permission denied when writing file
```

解决方案：
- 使用 root 用户：`user: "root"`
- 或者确保目标目录权限正确
- 检查文件所有者和权限

## 性能优化

1. **镜像缓存**: 预构建镜像而不是每次使用官方镜像
2. **容器复用**: 对于多个任务，可以复用同一个容器
3. **并行评估**: 同时运行多个容器（注意资源限制）
4. **最小化镜像**: 使用 `os_environment_minimal.Dockerfile`

## 扩展功能

### 自定义 Dockerfile

根据你的需求修改 `Environment/Dockerfiles/os_environment.Dockerfile`：

```dockerfile
FROM ubuntu:22.04

# 安装你需要的工具
RUN apt-get update && apt-get install -y \
    your-tool-1 \
    your-tool-2 \
    && rm -rf /var/lib/apt/lists/*

# 其他自定义配置
```

### 持久化存储

```python
config = {
    "image": "ubuntu:22.04",
    # 挂载卷（注意安全性）
    "volumes": {
        "/path/on/host": {
            "bind": "/path/in/container",
            "mode": "ro"  # 只读
        }
    }
}
```

## 常见问题

**Q: 是否支持 Windows 容器？**
A: 目前只支持 Linux 容器（ubuntu 等）。

**Q: 如何调试容器内的问题？**
A: 设置 `auto_remove: False`，然后使用 `docker exec -it <container_name> bash` 进入容器。

**Q: 性能开销如何？**
A: Docker 容器启动需要 1-3 秒，命令执行几乎无开销。

**Q: 支持 GPU 吗？**
A: 需要安装 nvidia-docker 并配置相应参数。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

与主项目许可证相同。
