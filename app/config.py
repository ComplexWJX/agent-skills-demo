from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: Literal["auto", "openai", "deepseek"] = "auto"
    llm_api_key: SecretStr
    llm_model: str = Field(min_length=1)
    llm_base_url: str | None = None
    agent_model_call_limit: int = Field(default=8, ge=1, le=32)
    agent_tool_call_limit: int = Field(default=12, ge=1, le=64)
    agent_recursion_limit: int = Field(default=100, ge=20, le=1000)
    app_api_token: SecretStr = Field(min_length=16)
    app_request_timeout: float = Field(default=90, gt=0)
    app_max_concurrent: int = Field(default=4, ge=1)
    app_max_sessions: int = Field(default=100, ge=1)
    app_max_turns: int = Field(default=20, ge=1)

    @property
    def resolved_llm_provider(self) -> Literal["openai", "deepseek"]:
        """Resolve the provider, including legacy configs that only set URL/model."""
        if self.llm_provider != "auto":
            return self.llm_provider
        model = self.llm_model.lower()
        hostname = urlsplit(self.llm_base_url or "").hostname
        if model.startswith("deepseek") or "/deepseek" in model:
            return "deepseek"
        if hostname == "api.deepseek.com":
            return "deepseek"
        return "openai"

    @property
    def resolved_llm_base_url(self) -> str:
        """Return the provider endpoint unless an OpenAI-compatible proxy is configured."""
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.resolved_llm_provider == "deepseek":
            return "https://api.deepseek.com"
        return "https://api.openai.com/v1"

