from app.agents.market_researcher import MarketResearcher
from app.core.config import Settings
from app.llm.factory import ModelFactory
from app.services.web_search import WebSearchService


def test_mock_mode_automatically_calls_three_search_tools(tmp_path):
    calls: list[str] = []

    def fake_search(query: str, limit: int):
        calls.append(query)
        return [
            {
                "title": f"结果 {len(calls)}",
                "href": f"https://example.com/{len(calls)}",
                "body": "公开资料摘要",
            }
        ][:limit]

    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        upload_dir=tmp_path / "uploads",
        artifact_dir=tmp_path / "artifacts",
        llm_mode="mock",
        web_search_enabled=True,
    )
    service = WebSearchService(settings, search_callable=fake_search)
    researcher = MarketResearcher(settings, ModelFactory(settings), service)
    result = researcher.research(
        {
            "title": "医用低温冰箱",
            "functions": ["样本保存"],
            "indicators": [{"name": "温度", "target": "-80℃"}],
        }
    )

    assert len(calls) == 3
    assert {item["source_type"] for item in result["sources"]} == {
        "products",
        "vendors",
        "transactions",
    }
    assert result["mode"] == "deterministic_tools"
    assert result["products"] == []

