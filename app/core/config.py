from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "招标智能体后端"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/tender_agent.db"
    upload_dir: Path = Path("./data/uploads")
    artifact_dir: Path = Path("./data/artifacts")
    max_upload_mb: int = Field(default=30, gt=0, le=500)
    web_search_enabled: bool = True
    web_search_provider: Literal["duckduckgo"] = "duckduckgo"
    web_search_max_results: int = Field(default=6, ge=1, le=20)
    web_search_region: str = "cn-zh"
    web_search_timeout_seconds: int = Field(default=10, ge=1, le=60)

    llm_mode: Literal["mock", "openai_compatible"] = "mock"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    market_research_model: str | None = None
    tender_generation_model: str | None = None
    compliance_review_model: str | None = None
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_timeout_seconds: int = Field(default=90, gt=0)
    llm_max_retries: int = Field(default=2, ge=0, le=10)

    @field_validator("llm_base_url", "llm_api_key", "llm_model", mode="before")
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        return None if value == "" else value

    def prepare_directories(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        if self.database_url.startswith("sqlite:///"):
            db_path = Path(self.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

    def model_for(self, agent_type: str) -> str | None:
        specific = {
            "market_research": self.market_research_model,
            "tender_generation": self.tender_generation_model,
            "compliance_review": self.compliance_review_model,
        }.get(agent_type)
        return specific or self.llm_model


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
