# 验证记录

验证日期：2026-11-02。

## 环境

- Linux，CPython 3.12.14。
- 使用全新虚拟环境进行 `pip install -e './agent-skills-demo[dev]'`。
- LangChain 1.4.7，langchain-openai 1.7.3，LangGraph 1.2.19。
- 完整已安装依赖版本见 `requirements.lock.txt`。

## 运行结果

```text
python -m pytest -q
....................                                                     [100%]
20 passed in 1.08s
```

`python -m app.offline_demo` 成功运行真实的 LangChain Agent 图、工具执行器、
InMemorySaver、FastAPI lifespan 和 HTTP 测试客户端，返回当前轮的四个工具调用：

1. `load_skill`
2. `get_device_status`
3. `read_skill_reference`
4. `get_device_events`

测试还检查了 checkpoint 中的实际工具返回值，包括 900 秒心跳年龄和规则文档内容，
而不只检查模型提出的工具名称。统计测试核验了 6 个样本、120.83 秒均值、
2 个超阈值样本和 0.3333 的占比。

## 覆盖内容

- 仅元数据出现在 Skill 目录中，正文和参考文档按工具调用加载。
- YAML/目录名称校验、未知 Skill、文件大小上限。
- 绝对路径、上级目录、Windows 风格路径和符号链接越界读取防护。
- 排查 Skill 和统计 Skill 的完整图执行与 HTTP 请求。
- Bearer token、请求字段校验。
- 同会话上下文保存，不同会话隔离，当前轮轨迹不混入上一轮。
- 模型调用循环上限，以及失败会话拒绝继续使用。
- 会话数/轮数上限、请求超时、同会话并发控制。

## 验证边界

- 使用明确标注的 ScriptedChatModel，无真实模型 API 调用及费用。
- 未验证某个真实模型是否正确选中 Skill、遵循步骤或给出高质量诊断。
- 未连接真实设备、数据库或业务接口。
- 未运行多进程/分布式负载测试，未在 Windows 或其他 Python 版本实测。
- README 中 Deep Agents 片段仅作另一种接法的说明，未纳入已运行测试。

