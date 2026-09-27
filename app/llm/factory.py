from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import Settings


class ModelFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def model_name(self, agent_type: str) -> str:
        if self.settings.llm_mode == "mock":
            return "mock"
        return self.settings.model_for(agent_type) or "unconfigured"

    def create(self, agent_type: str) -> ChatOpenAI | None:
        if self.settings.llm_mode == "mock":
            return None
        model = self.settings.model_for(agent_type)
        if not model or not self.settings.llm_api_key:
            raise RuntimeError("openai_compatible 模式需要配置模型名称和 LLM_API_KEY")
        return ChatOpenAI(
            model=model,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            temperature=self.settings.llm_temperature,
            timeout=self.settings.llm_timeout_seconds,
            max_retries=self.settings.llm_max_retries,
        )

