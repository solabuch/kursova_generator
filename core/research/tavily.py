# core/research/tavily.py
"""Tavily Search — платний web-пошук (pay-as-you-go). Для контексту без peer-review."""
import hashlib
import logging
from typing import Optional

import httpx

from core.models import Source

logger = logging.getLogger(__name__)


class TavilyClient:
    def __init__(self, api_key: Optional[str], max_results: int = 5):
        self.api_key = api_key
        self.max_results = max_results

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, client: httpx.AsyncClient) -> list[Source]:
        if not self.enabled:
            return []

        try:
            r = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": self.max_results,
                    "include_raw_content": False,
                },
                timeout=25.0,
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            logger.warning(f"Tavily error для '{query}': {e}")
            return []

        sources: list[Source] = []
        for res in data.get("results", []):
            url = res.get("url") or ""
            if not url:
                continue
            sid = hashlib.md5(url.encode()).hexdigest()[:12]
            sources.append(Source(
                id=sid,
                title=res.get("title") or url,
                source_type="web",
                url=url,
                abstract=(res.get("content") or "")[:500] or None,
            ))
        logger.info(f"Tavily: '{query}' → {len(sources)} web-результатів")
        return sources
