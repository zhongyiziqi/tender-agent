from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.core.config import Settings


SearchCallable = Callable[[str, int], list[dict[str, Any]]]


class WebSearchService:
    """Keyless web-search adapter used by market-research tools."""

    def __init__(self, settings: Settings, search_callable: SearchCallable | None = None) -> None:
        self.settings = settings
        self._search_callable = search_callable

    def search(self, query: str, max_results: int | None = None) -> list[dict[str, Any]]:
        if not self.settings.web_search_enabled:
            return []
        limit = max_results or self.settings.web_search_max_results
        if self._search_callable:
            raw_results = self._search_callable(query, limit)
        else:
            raw_results = DDGS(timeout=self.settings.web_search_timeout_seconds).text(
                query,
                region=self.settings.web_search_region,
                safesearch="moderate",
                max_results=limit,
            )
        results: list[dict[str, Any]] = []
        for item in raw_results[:limit]:
            url = item.get("href") or item.get("url")
            if not url:
                continue
            results.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "url": str(url).strip(),
                    "snippet": str(item.get("body") or item.get("snippet") or "").strip(),
                    "query": query,
                }
            )
        return results

    def fetch_page(self, url: str) -> dict[str, str]:
        with httpx.Client(
            timeout=self.settings.web_search_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": "TenderAgentResearch/0.1"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise ValueError(f"暂不解析该网页内容类型: {content_type or 'unknown'}")
        if len(response.content) > 2 * 1024 * 1024:
            raise ValueError("网页内容超过 2 MB 限制")
        if "text/html" in content_type:
            soup = BeautifulSoup(response.text, "html.parser")
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
            title = soup.title.string.strip() if soup.title and soup.title.string else ""
        else:
            text = response.text
            title = ""
        return {"url": url, "title": title, "content": text[:20000]}
