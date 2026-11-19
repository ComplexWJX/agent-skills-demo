import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.agent import build_agent, build_chat_model
from app.config import PROJECT_ROOT, Settings
from app.main import create_app
from app.offline_demo import ScriptedChatModel, TRIAGE_STEPS, REPORT_STEPS, call
from app.service import AgentService, BusyError, SessionLimitError
from app.skills import SkillRegistry
from app.tools import (DeviceRepository, build_tools, parse_lookup_model_output,
                       parse_pending_keywords_output, parse_script_result)

TOKEN = "offline-test-token"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def settings(**changes):
    values = {
        "llm_provider": "openai",
        "llm_api_key": "not-used",
        "llm_model": "scripted",
        "llm_base_url": None,
        "app_api_token": TOKEN,
    }
    values.update(changes)
    return Settings(**values)


def test_provider_defaults_and_deepseek_chat_options(monkeypatch):
    openai_settings = settings()
    assert openai_settings.resolved_llm_provider == "openai"
    assert openai_settings.resolved_llm_base_url == "https://api.openai.com/v1"

    deepseek_settings = settings(llm_provider="deepseek", llm_base_url=None)
    assert deepseek_settings.resolved_llm_provider == "deepseek"
    assert deepseek_settings.resolved_llm_base_url == "https://api.deepseek.com"

    captured = {}
    sentinel = object()

    def fake_chat_openai(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr("app.agent.ChatOpenAI", fake_chat_openai)
    assert build_chat_model(deepseek_settings) is sentinel
    assert captured["model"] == "scripted"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["use_responses_api"] is False
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}


@pytest.mark.parametrize(
    ("model", "base_url"),
    [
        ("deepseek-flash", None),
        ("some-model", "https://api.deepseek.com/"),
    ],
)
def test_auto_provider_detects_deepseek(model, base_url):
    configured = settings(llm_provider="auto", llm_model=model, llm_base_url=base_url)
    assert configured.resolved_llm_provider == "deepseek"


def test_custom_provider_endpoint_is_normalized():
    configured = settings(llm_provider="deepseek", llm_base_url="https://proxy.example/v1/")
    assert configured.resolved_llm_base_url == "https://proxy.example/v1"


def test_full_skill_tool_api_trajectory():
    app = create_app(settings(), ScriptedChatModel(responses=TRIAGE_STEPS))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/skills").status_code == 401
        catalog = client.get("/skills", headers=HEADERS).json()
        names = {skill["name"] for skill in catalog}
        assert {"device-triage", "heartbeat-report"}.issubset(names)
        assert all("instructions" not in skill for skill in catalog)
        response = client.post("/chat", headers=HEADERS,
                               json={"session_id": "triage", "message": "排查 ONU1001 离线"})
        assert response.status_code == 200, response.text
        assert [c["name"] for c in response.json()["tool_calls"]] == [
            "load_skill", "get_device_status", "read_skill_reference", "get_device_events"]
        # Verify actual ToolMessages in the real LangGraph checkpoint, not just
        # the scripted model's proposed tool-call names.
        state = app.state.service.agent.get_state({"configurable": {"thread_id": "triage"}})
        outputs = {m.name: json.loads(m.content) for m in state.values["messages"]
                   if isinstance(m, ToolMessage)}
        assert outputs["get_device_status"]["heartbeat_age_seconds"] == 900
        assert "业务心跳超时" in outputs["read_skill_reference"]["content"]
        assert outputs["get_device_events"]["events"][-1]["type"] == "ping-sent"
        assert "instructions" in outputs["load_skill"]


def test_report_uses_deterministic_statistics():
    app = create_app(settings(), ScriptedChatModel(responses=REPORT_STEPS))
    with TestClient(app) as client:
        response = client.post("/chat", headers=HEADERS,
                               json={"session_id": "report", "message": "统计 ONU1001 心跳"})
        assert response.status_code == 200, response.text
        state = app.state.service.agent.get_state({"configurable": {"thread_id": "report"}})
        output = next(json.loads(m.content) for m in state.values["messages"]
                      if isinstance(m, ToolMessage) and m.name == "summarize_heartbeat_intervals")
        assert output["sample_count"] == 6
        assert output["mean_seconds"] == 120.83
        assert output["exceeding_count"] == 2
        assert output["exceeding_ratio"] == 0.3333


class HistoryModel(ScriptedChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        text = "|".join(str(m.content) for m in messages if isinstance(m, HumanMessage))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


def test_same_session_remembers_and_other_session_isolated():
    app = create_app(settings(), HistoryModel(responses=[]))
    with TestClient(app) as client:
        def send(session, text):
            response = client.post("/chat", headers=HEADERS,
                                   json={"session_id": session, "message": text})
            assert response.status_code == 200, response.text
            return response.json()
        assert send("a", "first")["answer"] == "first"
        second = send("a", "second")
        assert second["answer"] == "first|second"
        assert second["tool_calls"] == []
        assert send("b", "other")["answer"] == "other"


def test_current_turn_trace_excludes_previous_turn_calls():
    app = create_app(settings(), ScriptedChatModel(responses=REPORT_STEPS))
    with TestClient(app) as client:
        body = {"session_id": "repeat", "message": "统计 ONU1001"}
        first = client.post("/chat", headers=HEADERS, json=body)
        second = client.post("/chat", headers=HEADERS, json=body)
        assert first.status_code == second.status_code == 200
        assert len(second.json()["tool_calls"]) == 2


def test_invalid_request_and_token():
    app = create_app(settings(), ScriptedChatModel(responses=[AIMessage(content="ok")]))
    with TestClient(app) as client:
        assert client.post("/chat", json={"session_id": "a", "message": "hi"}).status_code == 401
        assert client.post("/chat", headers=HEADERS,
                           json={"session_id": "../bad", "message": "hi"}).status_code == 422


def test_call_limit_stops_loop_and_marks_session_failed():
    loop = call("load_skill", {"skill_name": "device-triage"}, "repeat")
    app = create_app(settings(), ScriptedChatModel(responses=[loop]))
    with TestClient(app) as client:
        body = {"session_id": "loop", "message": "loop"}
        response = client.post("/chat", headers=HEADERS, json=body)
        assert response.status_code == 508
        assert "安全上限" in response.json()["detail"]
        assert client.post("/chat", headers=HEADERS, json=body).status_code == 409


def test_turn_and_session_limits():
    app = create_app(settings(app_max_turns=1, app_max_sessions=1),
                     ScriptedChatModel(responses=[AIMessage(content="ok")]))
    with TestClient(app) as client:
        assert client.post("/chat", headers=HEADERS,
                           json={"session_id": "one", "message": "hi"}).status_code == 200
        assert client.post("/chat", headers=HEADERS,
                           json={"session_id": "one", "message": "again"}).status_code == 409
        assert client.post("/chat", headers=HEADERS,
                           json={"session_id": "two", "message": "hi"}).status_code == 409


def test_unknown_device_and_reference_error_are_tool_results():
    tools = {t.name: t for t in build_tools(SkillRegistry(PROJECT_ROOT / "skills"),
                                          DeviceRepository(PROJECT_ROOT / "data/devices.json"))}
    assert tools["get_device_status"].invoke({"device_id": "missing"})["error"] == "device_not_found"
    assert tools["read_skill_reference"].invoke(
        {"skill_name": "device-triage", "relative_path": "../../.env"})["error"] == "reference_unavailable"
    assert "pending_keywords" in tools


def test_parse_pending_keywords_output():
    output = (
        "关键字\t规约规则\t行数\t主要vendorClass\tvendorClass分布\t样例主机名\n"
        "XIAOMI-12S-ULTRA\t原文\t1\t主机名回声\t主机名回声:1\tXiaomi-12S-Ultra\n"
        "ZXHN E1630\t去掉MAC后缀\t2\tudhcp\tudhcp:2\tZXHN E1630-aa:bb:cc:dd:ee:ff\n"
        "shown 2\nremaining 7\n"
    )
    parsed = parse_pending_keywords_output(output)
    assert parsed["shown"] == 2
    assert parsed["remaining"] == 7
    assert parsed["keywords"][0]["关键字"] == "XIAOMI-12S-ULTRA"
    assert parsed["keywords"][1]["规约规则"] == "去掉MAC后缀"


@pytest.mark.parametrize("output, expected", [
    (
        "MATCH\n厂商\t小米\n类别\t手机\n型号\t12S Ultra\n"
        "来源\thttps://example.test/model\n属性键\tcpu,mem,release_time\n同名\t是\n",
        {"status": "MATCH", "型号": "12S Ultra", "同名": "是"},
    ),
    (
        "NEW\n属性键\tcpu,mem,release_time\n同名\t否\n",
        {"status": "NEW", "属性键": "cpu,mem,release_time", "同名": "否"},
    ),
])
def test_parse_lookup_model_match_and_new(output, expected):
    parsed = parse_lookup_model_output(output)
    for key, value in expected.items():
        assert parsed[key] == value


def test_parse_lookup_model_ambiguous():
    parsed = parse_lookup_model_output(
        "AMBIGUOUS\n小米\t手机\t12S Ultra\n红米\t手机\t12 Ultra\ncount 4\n"
    )
    assert parsed == {
        "status": "AMBIGUOUS",
        "candidates": [
            {"厂商": "小米", "类别": "手机", "型号": "12S Ultra"},
            {"厂商": "红米", "类别": "手机", "型号": "12 Ultra"},
        ],
        "count": 4,
    }


def test_script_output_parse_errors_are_tool_results():
    result = parse_script_result(
        {"returncode": 0, "stdout": "NEW\n", "stderr": ""},
        parse_lookup_model_output,
    )
    assert result["error"] == "invalid_script_output"
    assert "属性键" in result["detail"]


def test_timeout_invalidates_session():
    class SlowAgent:
        async def ainvoke(self, *args, **kwargs):
            await asyncio.sleep(1)

    async def scenario():
        service = AgentService(SlowAgent(), settings(app_request_timeout=0.01))
        with pytest.raises(TimeoutError):
            await service.chat("slow", "hi")
        with pytest.raises(SessionLimitError):
            await service.chat("slow", "hi")
        assert not service.slots.locked()
    asyncio.run(scenario())


def test_same_session_rejects_concurrent_turns():
    class BlockingAgent:
        def __init__(self):
            self.started = asyncio.Event()
            self.finish = asyncio.Event()

        async def ainvoke(self, *args, **kwargs):
            self.started.set()
            await self.finish.wait()
            return {"messages": [HumanMessage(content="hi"), AIMessage(content="ok")]}

    async def scenario():
        agent = BlockingAgent()
        service = AgentService(agent, settings())
        first = asyncio.create_task(service.chat("one", "hi"))
        await agent.started.wait()
        try:
            with pytest.raises(BusyError):
                await service.chat("one", "again")
        finally:
            agent.finish.set()
            await first
    asyncio.run(scenario())

