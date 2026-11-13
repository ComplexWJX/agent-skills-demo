import asyncio
from dataclasses import dataclass, field
import logging

from langchain_core.messages import AIMessage, HumanMessage

from app.config import Settings

logger = logging.getLogger(__name__)


class BusyError(Exception):
    pass


class SessionLimitError(Exception):
    pass


@dataclass
class Session:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    turns: int = 0
    failed: bool = False


class AgentService:
    def __init__(self, agent, settings: Settings):
        self.agent = agent
        self.settings = settings
        self.sessions: dict[str, Session] = {}
        self.slots = asyncio.Semaphore(settings.app_max_concurrent)

    async def chat(self, session_id: str, message: str) -> dict:
        # Called inside one event loop; no await between lookup and insertion.
        session = self.sessions.get(session_id)
        if session is None:
            if len(self.sessions) >= self.settings.app_max_sessions:
                raise SessionLimitError("演示实例的会话数已达上限，请重启实例清空")
            session = self.sessions[session_id] = Session()
        try:
            await asyncio.wait_for(session.lock.acquire(), timeout=0.1)
        except TimeoutError:
            raise BusyError("该会话正在处理上一条消息") from None
        try:
            # A failed/cancelled tool turn may have partial checkpoints. Reject
            # reuse so an unfinished tool call cannot corrupt the next turn.
            if session.failed:
                raise SessionLimitError("上次请求未完成，请使用新的 session_id")
            if session.turns >= self.settings.app_max_turns:
                raise SessionLimitError("该会话达到演示轮数上限，请使用新的 session_id")
            try:
                await asyncio.wait_for(self.slots.acquire(), timeout=0.1)
            except TimeoutError:
                raise BusyError("服务繁忙，请稍后重试") from None
            try:
                session.turns += 1
                result = await asyncio.wait_for(
                    self.agent.ainvoke(
                        {"messages": [{"role": "user", "content": message}]},
                        config={"configurable": {"thread_id": session_id}, "recursion_limit": 30},
                    ), timeout=self.settings.app_request_timeout,
                )
            except BaseException:
                session.failed = True
                raise
            finally:
                self.slots.release()

            messages = result["messages"]
            start = max(i for i, msg in enumerate(messages) if isinstance(msg, HumanMessage))
            current = messages[start + 1:]
            calls = [{"name": call["name"], "args": call["args"]}
                     for msg in current if isinstance(msg, AIMessage)
                     for call in msg.tool_calls]
            logger.info("agent_turn_complete session=%s tools=%s", session_id,
                        [call["name"] for call in calls])
            final = messages[-1]
            if isinstance(final.content, str):
                answer = final.content
            else:
                answer = "\n".join(block.get("text", "") for block in final.content
                                   if isinstance(block, dict) and block.get("type") == "text")
            return {"session_id": session_id, "answer": answer, "tool_calls": calls}
        finally:
            session.lock.release()

