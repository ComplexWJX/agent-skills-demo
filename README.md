# LangChain + Skills 简易 Agent 工程

这是一个可运行的 Python 后端示例：一个 LangChain Agent 根据任务按需加载
`SKILL.md`，读取参考文档，再调用明确注册的业务工具，由 FastAPI 提供接口。

示例业务是设备离线排查和心跳质量报告。数据完全来自 `data/devices.json` 的
固定测试快照，不会访问真实设备、数据库，也不会修改设备状态。

## 1. Skill 到底怎样起作用

Skill 是“任务操作说明 + 可选资源”，不是一个新的模型，也不是 Python 函数本身。

| 组件 | 在本工程中的作用 |
| --- | --- |
| 模型 | 理解问题，决定加载哪个 Skill、调用哪个工具、如何组织答案 |
| LangChain `create_agent` | 执行模型与工具之间的循环 |
| `SKILL.md` | 描述何时使用、操作顺序、判断口径、输出格式 |
| `references/*.md` | 需要时再读入的详细规则 |
| `@tool` Python 函数 | 真正执行查询、统计等确定性操作 |
| Checkpointer | 保存同一个 `session_id` 的消息和工具结果 |

本工程的执行顺序：

1. 服务启动：扫描 `skills/*/SKILL.md`，校验 YAML，仅把名称和用途放入系统提示词。
2. 用户提问：“排查 ONU1001 为什么离线”。
3. 模型依据目录，生成 `load_skill(skill_name="device-triage")` 工具调用。
4. LangChain 执行该 Python 工具，将 Skill 全文作为工具结果写回模型上下文。
5. 模型看到步骤后，调用设备查询和规则读取工具。
6. LangChain 执行这些工具，再把结果返回模型。
7. 模型根据说明和证据生成答案，不再发起工具调用时结束。

这里的“渐进加载”指逐步加入模型上下文；启动扫描时仍需读取文件来解析元数据。
同一会话中，已经读过的正文和工具结果随历史保留；新会话按需重新加载。
没有适用 Skill 的一般问题可以直接回答。

**创建目录不会让普通 LangChain Agent 自动识别 Skill。** 本工程通过
`SkillRegistry + load_skill + system_prompt` 明确搭起这层机制。

**Skill 里的步骤是模型遵循的说明，不是代码层的强制状态机。** 本工程把五个工具
都显式注册给同一个 Agent。它没有在加载 Skill 时动态授予工具权限，也没有强制
“必须先加载 Skill 才能调用业务工具”。若业务要求严格顺序、授权或审批，需在
工具实现、middleware 或 LangGraph 节点中执行校验。

Skill 不必依赖向量数据库。本示例通过名称和描述供模型选择；知识量变大后，可再
增加 RAG 检索工具，供 Skill 调用。RAG 提供相关资料，Skill 提供任务执行方法。

## 2. 文件职责

| 路径 | 内容 |
| --- | --- |
| `app/config.py` | 环境变量、密钥和运行上限 |
| `app/skills.py` | Skill 扫描、YAML 校验、正文加载、受限参考文档读取 |
| `app/tools.py` | 明确注册的业务工具和演示数据适配器 |
| `app/agent.py` | 模型、提示词、Skill 目录、工具、会话保存和调用上限 |
| `app/service.py` | 同会话串行、并发上限、请求超时、当前轮工具轨迹 |
| `app/main.py` | FastAPI 入口、Bearer token、请求校验与错误映射 |
| `app/offline_demo.py` | 不调用模型 API 的确定性集成演示 |
| `skills/device-triage/SKILL.md` | 离线排查步骤 |
| `skills/device-triage/references/offline-rules.md` | 离线判断口径 |
| `skills/heartbeat-report/SKILL.md` | 心跳统计报告步骤 |
| `data/devices.json` | 两台演示设备的固定快照 |
| `tests/` | Skill、工具、真实 Agent 图和 HTTP 接口的离线测试 |
| `requirements.lock.txt` | 验证环境导出的完整依赖版本 |
| `VERIFICATION.md` | 本次验证结果与验证边界 |

## 3. 安装与启动

需要 Python 3.11～3.13，实际验证版本见 `VERIFICATION.md`。请使用源码目录运行，
按下列方式做 editable 安装，保持 `app/`、`skills/` 和 `data/` 在同一项目根目录。

Windows PowerShell：

```powershell
cd agent-skills-demo
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# 不需要模型 API Key，先验证工程调用链
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m app.offline_demo

# 准备真实模型配置后启动
Copy-Item .env.example .env
# 编辑 .env，填写 LLM_API_KEY、LLM_MODEL 和 APP_API_TOKEN
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info
```

Linux / macOS：

```bash
cd agent-skills-demo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python -m app.offline_demo
cp .env.example .env
# 编辑 .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info
```

`.env` 示例：

```dotenv
LLM_PROVIDER=openai
LLM_API_KEY=你的模型API密钥
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=你有权限使用且支持工具调用的模型名
APP_API_TOKEN=本地接口访问令牌至少16字符
APP_REQUEST_TIMEOUT=90
APP_MAX_CONCURRENT=4
APP_MAX_SESSIONS=100
APP_MAX_TURNS=20
```

接入 DeepSeek 时使用其 OpenAI 兼容的 Chat Completions 地址：

```dotenv
LLM_PROVIDER=deepseek
LLM_API_KEY=你的DeepSeek API密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
APP_API_TOKEN=本地接口访问令牌至少16字符
```

`LLM_BASE_URL` 可省略，程序会按 `LLM_PROVIDER` 选择官方默认地址；保留该项可接入
兼容网关或代理。DeepSeek 分支会显式使用非思考模式，以稳定支持 Agent 的多轮
`tools` / `tool_calls` 调用。

模型必须支持原生工具调用，即 Chat Completions 中的 `tools` / `tool_calls`。
本示例用 `ChatOpenAI(..., use_responses_api=False)` 连接该协议；仅支持文本聊天的
接口不够。第三方服务是否完全兼容需要实测；也可按其官方集成包替换模型适配器。
模型密钥只放后端，前端仅携带本应用的访问令牌。

## 4. 调用接口

打开 http://127.0.0.1:8000/docs，可在 Authorize 中填入 `APP_API_TOKEN`，直接调试。

接口：`GET /health`、`GET /skills`、`POST /chat`。除健康检查外均要求 Bearer token。

Windows PowerShell：

```powershell
$headers = @{ Authorization = "Bearer 你在.env中设置的APP_API_TOKEN" }
$payload = @{
  session_id = "demo-001"
  message = "请排查 ONU1001 为什么离线，按证据说明。"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/chat" -Method Post `
  -Headers $headers -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($payload))
```

HTTP 请求体：

```json
{
  "session_id": "demo-001",
  "message": "请排查 ONU1001 为什么离线，按证据说明。"
}
```

一次可能的工具轨迹：

```text
load_skill(device-triage)
get_device_status(ONU1001)
read_skill_reference(device-triage, references/offline-rules.md)
get_device_events(ONU1001)
```

这只是一次可能的调用顺序；真实模型可能合并独立调用、询问缺少的参数，或复用同会话
已加载的内容。可直接检查响应的 `tool_calls`，判断模型是否实际加载了 Skill。

示例返回结构：

```json
{
  "session_id": "demo-001",
  "answer": "模型根据 Skill 和实际工具结果生成的回答",
  "tool_calls": [
    {"name": "load_skill", "args": {"skill_name": "device-triage"}},
    {"name": "get_device_status", "args": {"device_id": "ONU1001"}}
  ]
}
```

`tool_calls` 是当前轮的调用记录，包含失败尝试，不等价于业务动作全部成功；实际工具结果
保存在会话状态中。这里为了便于理解没有把完整模型消息、Skill 正文和工具结果全部回传。

沿用 `demo-001` 可继续问：“再帮我统计它的心跳间隔”。新建 `session_id` 得到独立上下文。

演示数据按 `2026-11-02T10:00:00+08:00` 判断：

| 设备 | 测试数据特征 |
| --- | --- |
| ONU1001 | 最后业务心跳距快照 900 秒，连接状态仍为 true，只有 ping 发送证据 |
| ONU1002 | 最后业务心跳距快照 30 秒 |

ONU1001 的统计样本为 `[60, 60, 65, 120, 180, 240]` 秒：均值 120.83 秒，最大 240 秒；
严格大于 120 秒的样本有 2 个，占比 33.33%。这些都是测试快照，不代表当前真实状态。

## 5. 增加自己的 Skill

新增 `skills/your-skill/SKILL.md`，其中目录名与 `name` 一致：

```markdown
---
name: your-skill
description: 明确写出什么任务和什么用户表达适合这个 Skill。
---

# 工作步骤

1. 收集必要参数，缺少参数先询问。
2. 调用已经注册的业务工具。
3. 按证据生成结果，并说明未能确认的部分。
```

如果需要规则文档，在其 `references/` 下新增 `.md`，并在正文写出路径、内容和读取时机。
本实现只允许通过 `read_skill_reference` 读取这个目录中的 Markdown 文件，单文件上限 64 KiB。

如果需要新增业务能力，在 `app/tools.py` 编写 `@tool` 函数，并加入 `build_tools()` 的返回列表。
Skill 中仅写工具名称不会自动创建、授权或执行工具。修改目录元数据或工具后重启服务。
正文和引用文档是按调用读取的，但旧会话已加载的旧文本不会自动消失；修改后用新会话验证。

格式支持范围：本工程仅支持 `name`、`description`、正文和 `references/*.md`。
它不是 Agent Skills 全规范运行时，不处理 `allowed-tools` 等其他可选字段，也不自动执行
`scripts/`。如确需运行脚本，应由后端提供带参数校验的专用工具，或另接受限执行环境。

## 6. 与 Deep Agents 的关系

LangChain 官方提供两条路线：

- 使用 `create_agent`，自行组合 Skill 加载工具：本工程采用此路线，核心机制清晰。
- 使用 `deepagents.create_deep_agent(..., skills=[...])`：由其 Skill middleware 发现
  元数据，配合文件工具按需读取说明，适合需要现成文件操作等能力时采用。

第二条路线的示意代码如下；它不属于本工程已运行的测试范围，`deepagents` 也未包含在依赖中：

```python
from pathlib import Path
from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

# model 是已初始化且支持工具调用的 LangChain chat model
root = Path.cwd().resolve()
agent = create_deep_agent(
    model=model,
    backend=FilesystemBackend(root_dir=str(root), virtual_mode=True),
    skills=["/skills/"],  # 相对 backend 根的虚拟目录，下面包含多个 Skill 子目录
    tools=business_tools,
)
result = agent.invoke({"messages": [{"role": "user", "content": "排查 ONU1001 离线"}]})
```

`virtual_mode=True` 用于限定文件路径命名空间，不等价于操作系统级沙箱。
是否提供脚本执行能力，取决于所选 backend 和已注册工具。

## 7. 工程边界与下一步

- 会话使用 `InMemorySaver`，重启会丢失；只运行一个 worker。多实例部署应改用共享
  数据库 checkpointer，并单独解决同一会话的跨进程串行和取消语义。
- 同一会话请求串行，繁忙返回 429；全局并发默认 4；达到会话/轮数上限返回 409。
  每轮最多 8 次模型调用、12 次工具调用，另有请求超时及图递归上限。
- 失败或超时可能已留下中间 checkpoint，该会话之后返回 409，要求使用新 ID。
  本工程不实现失败会话恢复协议；演示工具全部只读。
- 静态 Bearer token 面向本地单用户开发。`session_id` 不是身份认证；多人系统需要把
  已认证用户与会话绑定，并在数据适配器内验证设备归属与权限。
- Skill 文件只从项目内受信任来源加载。路径校验防止越界读取，但不能消除模型
  提示词注入，也不能替代真正的工具授权。不要在线接受任意第三方 Skill 安装包。
- 接真实设备时，替换 `DeviceRepository` 及查询工具。耗时网络工具优先实现为
  `async def` 并使用异步客户端；数据库连接由适配器负责池化、超时和清理。
- 对写库、重启设备、发通知等有副作用的动作，在代码中增加幂等、权限和必要审批。
- 生产会话需要历史裁剪或摘要、持久化数据保留策略。这里用会话数和轮数做演示上限，
  不提供持久化、自动清理、长期记忆、RAG、前端或流式输出。
- 离线测试验证工程运行机制；真实模型的 Skill 选择、步骤遵循和回答质量，需要用
  目标模型及自己的任务样本另做集成测试与评估。

## 官方参考

- LangChain Skills pattern: https://docs.langchain.com/oss/python/langchain/multi-agent/skills
- LangChain Agents: https://docs.langchain.com/oss/python/langchain/agents
- LangChain Tools: https://docs.langchain.com/oss/python/langchain/tools
- Short-term memory: https://docs.langchain.com/oss/python/langchain/short-term-memory
- Deep Agents Skills: https://docs.langchain.com/oss/python/deepagents/skills

