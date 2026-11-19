from contextlib import asynccontextmanager
import logging
import secrets

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.agent import build_agent
from app.config import PROJECT_ROOT, Settings
from app.service import AgentLoopError, AgentService, BusyError, SessionLimitError
from app.skills import SkillRegistry

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1, max_length=8000)


class ToolCall(BaseModel):
    name: str
    args: dict


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    tool_calls: list[ToolCall]


def create_app(settings: Settings | None = None, model=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        actual_settings = settings or Settings()
        registry = SkillRegistry(PROJECT_ROOT / "skills")
        app.state.settings = actual_settings
        app.state.registry = registry
        app.state.service = AgentService(build_agent(actual_settings, registry, model), actual_settings)
        yield

    application = FastAPI(title="Agent Skills Demo", lifespan=lifespan)

    def authenticate(request: Request,
                     credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        expected = request.app.state.settings.app_api_token.get_secret_value()
        if credentials is None or not secrets.compare_digest(credentials.credentials, expected):
            raise HTTPException(status_code=401, detail="Invalid API token",
                                headers={"WWW-Authenticate": "Bearer"})

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/skills", dependencies=[Depends(authenticate)])
    def skills(request: Request):
        return request.app.state.registry.catalog()

    @application.post("/chat", response_model=ChatResponse, dependencies=[Depends(authenticate)])
    async def chat(body: ChatRequest, request: Request):
        try:
            return await request.app.state.service.chat(body.session_id, body.message)
        except BusyError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from None
        except SessionLimitError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except AgentLoopError as exc:
            raise HTTPException(status_code=508, detail=str(exc)) from None
        except TimeoutError:
            raise HTTPException(status_code=504, detail="请求超时，请使用新的 session_id 重试") from None
        except Exception:
            logger.exception("Agent request failed")
            raise HTTPException(status_code=502,
                                detail="Agent 调用失败；检查服务端日志，并使用新的 session_id 重试") from None

    return application


app = create_app()

logger.info("Agent Skills Demo app initialized with settings.")