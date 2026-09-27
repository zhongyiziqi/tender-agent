from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import Settings
from app.llm.factory import ModelFactory
from app.services.web_search import WebSearchService


class ResearchedProduct(BaseModel):
    product_name: str
    vendor_name: str
    price: float | None = Field(default=None, gt=0)
    performance_score: float = Field(default=0, ge=0, le=100)
    service_score: float = Field(default=0, ge=0, le=100)
    meets_required: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    source_urls: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class HistoricalTransaction(BaseModel):
    product_name: str = ""
    purchaser: str = ""
    transaction_price: float | None = Field(default=None, gt=0)
    announcement_date: str | None = None
    source_url: str


class ResearchOutput(BaseModel):
    products: list[ResearchedProduct] = Field(default_factory=list)
    historical_transactions: list[HistoricalTransaction] = Field(default_factory=list)
    conclusion: str = ""


class MarketResearcher:
    def __init__(
        self,
        settings: Settings,
        model_factory: ModelFactory,
        search_service: WebSearchService,
    ) -> None:
        self.settings = settings
        self.model_factory = model_factory
        self.search_service = search_service

    @staticmethod
    def _queries(requirement: dict[str, Any]) -> dict[str, str]:
        indicators = " ".join(item.get("name", "") for item in requirement.get("indicators", []))
        functions = " ".join(requirement.get("functions", []))
        base = " ".join(part for part in [requirement.get("title", ""), functions, indicators] if part)
        return {
            "products": f"{base} 产品 型号 技术参数 厂商",
            "vendors": f"{base} 主流品牌 产品对比",
            "transactions": f"{base} 中标 成交公告 成交价格",
        }

    def research(self, requirement: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.web_search_enabled:
            return {
                "mode": "disabled",
                "search_queries": [],
                "sources": [],
                "products": [],
                "historical_transactions": [],
                "conclusion": "自动网络检索已关闭。",
            }
        if self.settings.llm_mode == "mock":
            return self._deterministic_search(requirement)
        return self._agent_search(requirement)

    def _deterministic_search(self, requirement: dict[str, Any]) -> dict[str, Any]:
        calls: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        errors: list[str] = []
        for category, query in self._queries(requirement).items():
            try:
                results = self.search_service.search(query)
            except Exception as exc:
                results = []
                errors.append(f"{category}: {exc}")
            calls.append({"tool": f"search_{category}", "query": query, "result_count": len(results)})
            sources.extend({**item, "source_type": category} for item in results)
        conclusion = "已自动检索产品、品牌和历史成交来源。"
        if errors:
            conclusion += "部分检索失败，需检查网络或更换搜索提供方。"
        conclusion += "mock 模式不进行大模型结构化抽取，搜索结果需人工确认。"
        return {
            "mode": "deterministic_tools",
            "search_queries": calls,
            "sources": sources,
            "products": [],
            "historical_transactions": [],
            "conclusion": conclusion,
            "errors": errors,
        }

    def _agent_search(self, requirement: dict[str, Any]) -> dict[str, Any]:
        model = self.model_factory.create("market_research")
        if model is None:
            return self._deterministic_search(requirement)

        calls: list[dict[str, Any]] = []
        all_sources: list[dict[str, Any]] = []

        def run_search(query: str, source_type: str) -> str:
            results = self.search_service.search(query)
            calls.append(
                {"tool": f"search_{source_type}", "query": query, "result_count": len(results)}
            )
            typed = [{**item, "source_type": source_type} for item in results]
            all_sources.extend(typed)
            return json.dumps(typed, ensure_ascii=False)

        def fetch_researched_page(url: str) -> str:
            allowed_urls = {item["url"] for item in all_sources}
            if url not in allowed_urls:
                raise ValueError("只能读取本次搜索结果中已经出现的 URL")
            return json.dumps(self.search_service.fetch_page(url), ensure_ascii=False)

        tools = [
            StructuredTool.from_function(
                name="search_products",
                description="搜索满足采购需求的产品、型号、生产厂商和公开技术参数。",
                func=lambda query: run_search(query, "products"),
            ),
            StructuredTool.from_function(
                name="search_vendors",
                description="搜索该品类的主流品牌、厂商和产品对比资料。",
                func=lambda query: run_search(query, "vendors"),
            ),
            StructuredTool.from_function(
                name="search_historical_transactions",
                description="搜索中标公告、成交公告、采购单位和成交价格。",
                func=lambda query: run_search(query, "transactions"),
            ),
            StructuredTool.from_function(
                name="fetch_researched_page",
                description="读取本次搜索结果中的产品页或公告页正文，用于核实参数、价格和成交信息。",
                func=fetch_researched_page,
            ),
        ]
        agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=(
                "你是采购人侧市场调研智能体。必须先调用搜索工具获取产品、厂商和历史成交资料，"
                "再判断哪些产品满足需求。不得使用训练记忆补造产品、价格或成交记录。"
                "每个产品必须包含本次工具返回的 source_urls；没有来源或证据不足时，"
                "meets_required 必须为 false，未知价格和参数保持为空。评分必须有公开参数依据。"
            ),
            response_format=ToolStrategy(ResearchOutput),
            name="market_research_tool_agent",
        )
        response = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "请自动调研满足以下采购需求的产品，并给出可追溯的候选产品、"
                            "历史成交记录和调研结论：\n"
                            + json.dumps(requirement, ensure_ascii=False)
                        ),
                    }
                ]
            }
        )
        structured = response.get("structured_response")
        if not isinstance(structured, ResearchOutput):
            raise RuntimeError("市场调研模型未返回约定的结构化结果")
        allowed_urls = {item["url"] for item in all_sources}
        products: list[dict[str, Any]] = []
        for product in structured.products:
            data = product.model_dump(mode="json")
            data["source_urls"] = [url for url in data["source_urls"] if url in allowed_urls]
            data["source_document_ids"] = []
            if not data["source_urls"]:
                data["meets_required"] = False
            products.append(data)
        transactions = []
        for transaction in structured.historical_transactions:
            if transaction.source_url in allowed_urls:
                transactions.append(transaction.model_dump(mode="json"))
        return {
            "mode": "langchain_tool_agent",
            "search_queries": calls,
            "sources": all_sources,
            "products": products,
            "historical_transactions": transactions,
            "conclusion": structured.conclusion,
            "errors": [],
        }
