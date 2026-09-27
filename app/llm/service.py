from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.factory import ModelFactory


class ModelService:
    def __init__(self, factory: ModelFactory) -> None:
        self.factory = factory

    def generate(self, agent_type: str, system: str, content: str, fallback: str) -> str:
        model = self.factory.create(agent_type)
        if model is None:
            return fallback
        response = model.invoke([SystemMessage(content=system), HumanMessage(content=content)])
        return str(response.content)

