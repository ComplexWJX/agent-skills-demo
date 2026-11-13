"""Deterministic integration demo. This model is a fixture, not an LLM.

Run: python -m app.offline_demo   (install the dev extra first)
"""
import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def call(name: str, args: dict, identifier: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": identifier}])


TRIAGE_STEPS = [
    call("load_skill", {"skill_name": "device-triage"}, "skill-1"),
    call("get_device_status", {"device_id": "ONU1001"}, "status-1"),
    call("read_skill_reference", {"skill_name": "device-triage",
         "relative_path": "references/offline-rules.md"}, "reference-1"),
    call("get_device_events", {"device_id": "ONU1001"}, "events-1"),
    AIMessage(content="离线集成测试：已读取 Skill、设备状态、判断口径和事件。"
                      "这是固定测试数据，观测时间为 2026-11-02 10:00 +08:00。"
                      "业务心跳超时；传输连接仍在，不能据此确认业务在线。"),
]

REPORT_STEPS = [
    call("load_skill", {"skill_name": "heartbeat-report"}, "skill-2"),
    call("summarize_heartbeat_intervals", {"device_id": "ONU1001"}, "stats-1"),
    AIMessage(content="固定测试快照：6 个样本，平均间隔 120.83 秒，"
                      "最长 240 秒，严格大于 120 秒的样本为 2 个，占比 33.33%。"),
]


class ScriptedChatModel(BaseChatModel):
    """Replay a predetermined tool trajectory to test the real graph/runtime.

    This does not test the judgment or answer quality of an actual LLM.
    """
    responses: list[AIMessage]

    @property
    def _llm_type(self) -> str:
        return "scripted-offline-fixture"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(self, messages: list[BaseMessage], stop=None,
                  run_manager=None, **kwargs: Any) -> ChatResult:
        last_user = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        step = sum(isinstance(m, AIMessage) for m in messages[last_user + 1:])
        response = self.responses[min(step, len(self.responses) - 1)].model_copy(deep=True)
        # Let the graph assign a fresh message ID on each turn.
        response.id = None
        return ChatResult(generations=[ChatGeneration(message=response)])


def main():
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.main import create_app

    settings = Settings(llm_api_key="offline-no-key", llm_model="scripted",
                        app_api_token="offline-demo-token")
    with TestClient(create_app(settings, ScriptedChatModel(responses=TRIAGE_STEPS))) as client:
        result = client.post("/chat", headers={"Authorization": "Bearer offline-demo-token"},
                             json={"session_id": "offline-1", "message": "排查 ONU1001 离线"})
        result.raise_for_status()
        print("NOTE: scripted model, no real LLM request was made.")
        print(json.dumps(result.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

