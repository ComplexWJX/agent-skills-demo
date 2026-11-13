from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    llm_provider: Literal["openai", "deepseek"] = "openai"
    llm_api_key: SecretStr
    llm_model: str = Field(min_length=1)
    llm_base_url: str | None = None
    app_api_token: SecretStr = Field(min_length=16)
    app_request_timeout: float = Field(default=90, gt=0)
    app_max_concurrent: int = Field(default=4, ge=1)
    app_max_sessions: int = Field(default=100, ge=1)
    app_max_turns: int = Field(default=20, ge=1)

    @property
    def resolved_llm_base_url(self) -> str:
        """Return the provider endpoint unless an OpenAI-compatible proxy is configured."""
        if self.llm_base_url:
            return self.llm_base_url.rstrip("/")
        if self.llm_provider == "deepseek":
            return "https://api.deepseek.com"
        return "https://api.openai.com/v1"

