from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.agents.market_researcher import MarketResearcher
from app.llm.factory import ModelFactory
from app.llm.service import ModelService
from app.repositories.repository import Repository
from app.services.rules import scan_compliance
from app.services.scoring import score_products


class WorkflowState(TypedDict, total=False):
    task_id: str
    input: dict[str, Any]
    requirement: dict[str, Any]
    evidence: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    scored_products: list[dict[str, Any]]
    source_text: str
    previous_result: dict[str, Any]
    web_research: dict[str, Any]
    findings: list[dict[str, Any]]
    result: dict[str, Any]


class WorkflowRunner:
    def __init__(
        self,
        repository: Repository,
        model_factory: ModelFactory,
        market_researcher: MarketResearcher,
    ) -> None:
        self.repository = repository
        self.model_factory = model_factory
        self.market_researcher = market_researcher
        self.models = ModelService(model_factory)
        self.market_graph = self._build_market_graph()
        self.tender_graph = self._build_tender_graph()
        self.compliance_graph = self._build_compliance_graph()

    def _log(self, state: WorkflowState, node: str, sources: list[dict[str, Any]] | None = None) -> None:
        task = self.repository.get_task(state["task_id"])
        agent_type = task.task_type if task else "unknown"
        self.repository.add_run(
            state["task_id"], node, self.model_factory.model_name(agent_type), sources or []
        )

    def run(self, task_id: str, task_type: str, input_data: dict[str, Any]) -> dict[str, Any]:
        graph = {
            "market_research": self.market_graph,
            "tender_generation": self.tender_graph,
            "compliance_review": self.compliance_graph,
        }.get(task_type)
        if graph is None:
            raise ValueError(f"不支持的任务类型: {task_type}")
        state = graph.invoke({"task_id": task_id, "input": input_data})
        return state["result"]

    def _build_market_graph(self):
        graph = StateGraph(WorkflowState)

        def validate(state: WorkflowState) -> dict[str, Any]:
            requirement = state["input"].get("requirement") or {}
            if not requirement.get("title"):
                raise ValueError("采购需求标题不能为空")
            for document_id in state["input"].get("document_ids", []):
                if not self.repository.get_document(document_id):
                    raise ValueError(f"资料文档不存在: {document_id}")
            self._log(state, "validate_requirement")
            return {"requirement": requirement}

        def structure(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "structure_requirement")
            return {"requirement": state["requirement"]}

        def retrieve(state: WorkflowState) -> dict[str, Any]:
            requirement = state["requirement"]
            query_parts = [requirement.get("title", "")]
            query_parts.extend(requirement.get("functions", []))
            query_parts.extend(item.get("name", "") for item in requirement.get("indicators", []))
            evidence = self.repository.search_chunks(
                " ".join(query_parts), state["input"].get("document_ids", []), limit=20
            )
            self._log(state, "retrieve_evidence", evidence)
            return {"evidence": evidence}

        def web_research(state: WorkflowState) -> dict[str, Any]:
            research = self.market_researcher.research(state["requirement"])
            self._log(state, "call_market_research_tools", research.get("sources", []))
            return {"web_research": research}

        def extract(state: WorkflowState) -> dict[str, Any]:
            candidates = list(state["input"].get("candidate_products", []))
            candidates.extend(state.get("web_research", {}).get("products", []))
            deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
            for candidate in candidates:
                key = (
                    str(candidate.get("vendor_name", "")).strip().lower(),
                    str(candidate.get("product_name", "")).strip().lower(),
                )
                if key != ("", "") and key not in deduplicated:
                    deduplicated[key] = candidate
            candidates = list(deduplicated.values())
            sources = state.get("evidence", []) + state.get("web_research", {}).get("sources", [])
            self._log(state, "extract_candidates", sources)
            return {"candidates": candidates}

        def filter_candidates(state: WorkflowState) -> dict[str, Any]:
            candidates = [item for item in state["candidates"] if item.get("meets_required", True)]
            self._log(state, "filter_required_indicators")
            return {"candidates": candidates}

        def score(state: WorkflowState) -> dict[str, Any]:
            weights = state["input"]["weights"]
            scored = score_products(state["candidates"], weights)
            self._log(state, "score_products")
            return {"scored_products": scored}

        def rank(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "rank_products")
            return {"scored_products": state["scored_products"]}

        def compile_report(state: WorkflowState) -> dict[str, Any]:
            products = state.get("scored_products", [])
            evidence = state.get("evidence", [])
            web_research_result = state.get("web_research", {})
            web_sources = web_research_result.get("sources", [])
            review_items: list[dict[str, str]] = []
            if not products:
                review_items.append(
                    {
                        "category": "资料完整性",
                        "severity": "high",
                        "message": (
                            "自动检索后仍未形成可验证候选产品；请配置真实模型进行结构化抽取，"
                            "或补充产品资料。"
                        ),
                    }
                )
            elif len(products) < 3:
                review_items.append(
                    {
                        "category": "厂商覆盖性",
                        "severity": "medium",
                        "message": "满足必达指标的候选产品不足三家，请补充市场资料。",
                    }
                )
            if not evidence and not web_sources:
                review_items.append(
                    {
                        "category": "来源追溯",
                        "severity": "medium",
                        "message": "未检索到上传资料来源，参数和成交信息需人工补充佐证。",
                    }
                )
            fallback = (
                f"已对 {len(products)} 个满足必达条件的候选产品进行可解释评分；"
                "结果仅基于用户提交的数据和资料。"
            )
            summary = self.models.generate(
                "market_research",
                "你是采购人侧市场调研助手。仅总结提供的数据，不得补造厂商、价格或成交记录。",
                json.dumps(
                    {"products": products, "evidence": (evidence + web_sources)[:10]},
                    ensure_ascii=False,
                ),
                fallback,
            )
            status = "needs_review" if not products else "completed"
            result = {
                "status": status,
                "agent_type": "market_research",
                "requirement": state["requirement"],
                "weights": state["input"]["weights"],
                "products": products,
                "top_three": products[:3],
                "historical_transactions": web_research_result.get("historical_transactions", []),
                "evidence": evidence + web_sources,
                "web_research": {
                    "mode": web_research_result.get("mode", "disabled"),
                    "search_queries": web_research_result.get("search_queries", []),
                    "conclusion": web_research_result.get("conclusion", ""),
                    "errors": web_research_result.get("errors", []),
                },
                "summary": summary,
                "review_items": review_items,
                "disclaimer": "调研结果须经采购人复核，不构成最终采购决策。",
            }
            self._log(state, "compile_market_report", evidence + web_sources)
            return {"result": result}

        for name, node in [
            ("validate", validate),
            ("structure", structure),
            ("retrieve", retrieve),
            ("web_research", web_research),
            ("extract", extract),
            ("filter", filter_candidates),
            ("score", score),
            ("rank", rank),
            ("report", compile_report),
        ]:
            graph.add_node(name, node)
        graph.add_edge(START, "validate")
        graph.add_edge("validate", "structure")
        graph.add_edge("structure", "retrieve")
        graph.add_edge("retrieve", "web_research")
        graph.add_edge("web_research", "extract")
        graph.add_edge("extract", "filter")
        graph.add_edge("filter", "score")
        graph.add_edge("score", "rank")
        graph.add_edge("rank", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def _build_tender_graph(self):
        graph = StateGraph(WorkflowState)

        def load_market(state: WorkflowState) -> dict[str, Any]:
            market_task_id = state["input"]["market_research_task_id"]
            task = self.repository.get_task(market_task_id)
            if not task or task.task_type != "market_research":
                raise ValueError("市场调研任务不存在")
            if task.status not in {"completed", "needs_review"} or not task.output_json:
                raise ValueError("市场调研任务尚未产生可用结果")
            result = json.loads(task.output_json)
            self._log(state, "load_market_result")
            return {"previous_result": result}

        def validate_top_three(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "validate_top_three")
            return {"previous_result": state["previous_result"]}

        def common_parameters(state: WorkflowState) -> dict[str, Any]:
            top_three = state["previous_result"].get("top_three", [])
            common: dict[str, Any] = {}
            if len(top_three) >= 3:
                first = top_three[0].get("parameters", {})
                for key, value in first.items():
                    if all(item.get("parameters", {}).get(key) == value for item in top_three[1:]):
                        common[key] = value
            previous = {**state["previous_result"], "common_parameters": common}
            self._log(state, "derive_common_parameters")
            return {"previous_result": previous}

        def exclusivity_check(state: WorkflowState) -> dict[str, Any]:
            common = state["previous_result"].get("common_parameters", {})
            text = json.dumps(common, ensure_ascii=False)
            findings = [item for item in scan_compliance(text, 3) if item["category"] != "厂商覆盖性"]
            self._log(state, "precheck_exclusivity")
            return {"findings": findings}

        def draft_sections(state: WorkflowState) -> dict[str, Any]:
            market = state["previous_result"]
            requirement = market.get("requirement", {})
            sections = {
                "采购项目概述": requirement.get("title", "未命名采购项目"),
                "采购需求": {
                    "functions": requirement.get("functions", []),
                    "required_indicators": [
                        item for item in requirement.get("indicators", []) if item.get("required", True)
                    ],
                },
                "技术参数草案": market.get("common_parameters", {}),
                "商务条款草案": {
                    "服务要求": requirement.get("service_requirements", []),
                    "预算上限": requirement.get("budget_max"),
                },
                "评分办法": market.get("weights", {}),
            }
            market["sections"] = sections
            self._log(state, "draft_tender_sections")
            return {"previous_result": market}

        def rule_review(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "review_tender_rules")
            return {"findings": state.get("findings", [])}

        def compile_draft(state: WorkflowState) -> dict[str, Any]:
            market = state["previous_result"]
            top_three = market.get("top_three", [])
            review_items = list(market.get("review_items", []))
            if len(top_three) < 3:
                review_items.append(
                    {
                        "category": "厂商覆盖性",
                        "severity": "high",
                        "message": "综合排名中不足三家合格产品，不能直接形成正式参数。",
                    }
                )
            if not market.get("common_parameters"):
                review_items.append(
                    {
                        "category": "技术参数",
                        "severity": "medium",
                        "message": "未提取到三家产品共同参数，需要人工编制或补充结构化参数。",
                    }
                )
            status = "completed" if len(top_three) >= 3 and not state.get("findings") else "needs_review"
            result = {
                "status": status,
                "agent_type": "tender_generation",
                "source_market_task_id": state["input"]["market_research_task_id"],
                "top_three": top_three,
                "vendor_coverage_count": len(top_three),
                "common_parameters": market.get("common_parameters", {}),
                "sections": market.get("sections", {}),
                "risk_findings": state.get("findings", []),
                "review_items": review_items,
                "draft_notice": "本文件为采购人侧招标文件草案，必须经人工确认后使用。",
            }
            self._log(state, "compile_tender_draft")
            return {"result": result}

        for name, node in [
            ("load", load_market),
            ("validate", validate_top_three),
            ("common", common_parameters),
            ("exclusivity", exclusivity_check),
            ("draft", draft_sections),
            ("review", rule_review),
            ("compile", compile_draft),
        ]:
            graph.add_node(name, node)
        graph.add_edge(START, "load")
        graph.add_edge("load", "validate")
        graph.add_edge("validate", "common")
        graph.add_edge("common", "exclusivity")
        graph.add_edge("exclusivity", "draft")
        graph.add_edge("draft", "review")
        graph.add_edge("review", "compile")
        graph.add_edge("compile", END)
        return graph.compile()

    def _build_compliance_graph(self):
        graph = StateGraph(WorkflowState)

        def parse_source(state: WorkflowState) -> dict[str, Any]:
            input_data = state["input"]
            if input_data.get("generation_task_id"):
                task = self.repository.get_task(input_data["generation_task_id"])
                if not task or task.task_type != "tender_generation" or not task.output_json:
                    raise ValueError("招标文件生成任务不存在或尚无结果")
                previous = json.loads(task.output_json)
                source_text = json.dumps(previous.get("sections", {}), ensure_ascii=False)
                coverage = previous.get("vendor_coverage_count")
            else:
                document = self.repository.get_document(input_data["document_id"])
                if not document:
                    raise ValueError("待检测文档不存在")
                chunks = self.repository.get_document_chunks(document.id)
                source_text = "\n".join(item.content for item in chunks)
                coverage = input_data.get("vendor_coverage_count")
            self._log(state, "parse_tender_document")
            return {
                "source_text": source_text,
                "previous_result": {"vendor_coverage_count": coverage},
            }

        def hard_rules(state: WorkflowState) -> dict[str, Any]:
            findings = scan_compliance(
                state["source_text"], state["previous_result"].get("vendor_coverage_count")
            )
            self._log(state, "scan_hard_rules")
            return {"findings": findings}

        def sensitive_terms(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "scan_sensitive_terms")
            return {"findings": state["findings"]}

        def semantic_review(state: WorkflowState) -> dict[str, Any]:
            fallback = "已完成确定性规则检查；复杂条款仍需采购或法务人员结合项目背景复核。"
            summary = self.models.generate(
                "compliance_review",
                "你是采购人侧招标文件审查助手。不得替代法律结论，只能基于提供文本提出风险提示。",
                state["source_text"][:12000],
                fallback,
            )
            previous = {**state["previous_result"], "semantic_summary": summary}
            self._log(state, "semantic_compliance_review")
            return {"previous_result": previous}

        def coverage(state: WorkflowState) -> dict[str, Any]:
            self._log(state, "verify_vendor_coverage")
            return {"findings": state["findings"]}

        def merge(state: WorkflowState) -> dict[str, Any]:
            severity_order = {"high": 0, "medium": 1, "low": 2}
            findings = sorted(
                state["findings"], key=lambda item: (severity_order.get(item["severity"], 9), item["rule_id"])
            )
            self._log(state, "merge_findings")
            return {"findings": findings}

        def compile_report(state: WorkflowState) -> dict[str, Any]:
            findings = state["findings"]
            high_count = sum(item["severity"] == "high" for item in findings)
            result = {
                "status": "needs_review" if high_count else "completed",
                "agent_type": "compliance_review",
                "summary": state["previous_result"].get("semantic_summary"),
                "vendor_coverage_count": state["previous_result"].get("vendor_coverage_count"),
                "risk_counts": {
                    level: sum(item["severity"] == level for item in findings)
                    for level in ("high", "medium", "low")
                },
                "findings": findings,
                "review_items": [
                    {
                        "category": item["category"],
                        "severity": item["severity"],
                        "message": item["suggestion"],
                    }
                    for item in findings
                ],
                "disclaimer": "检测结果为辅助意见，不替代采购、法务或监管部门的最终判断。",
            }
            self._log(state, "compile_compliance_report")
            return {"result": result}

        for name, node in [
            ("parse", parse_source),
            ("hard_rules", hard_rules),
            ("sensitive_terms", sensitive_terms),
            ("semantic", semantic_review),
            ("coverage", coverage),
            ("merge", merge),
            ("report", compile_report),
        ]:
            graph.add_node(name, node)
        graph.add_edge(START, "parse")
        graph.add_edge("parse", "hard_rules")
        graph.add_edge("hard_rules", "sensitive_terms")
        graph.add_edge("sensitive_terms", "semantic")
        graph.add_edge("semantic", "coverage")
        graph.add_edge("coverage", "merge")
        graph.add_edge("merge", "report")
        graph.add_edge("report", END)
        return graph.compile()
