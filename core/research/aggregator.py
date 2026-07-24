# core/research/aggregator.py
"""Паралельно опитує провайдерів, дедуплікує, кешує."""
import asyncio
import logging
from typing import Optional

import httpx

from core.models import Source
from core.research.openalex import OpenAlexClient
from core.research.tavily import TavilyClient

logger = logging.getLogger(__name__)


class ResearchAggregator:
    def __init__(
        self,
        openalex: OpenAlexClient,
        tavily: Optional[TavilyClient] = None,
    ):
        self.openalex = openalex
        self.tavily = tavily
        self._cache: dict[str, list[Source]] = {}
        self._lock = asyncio.Lock()

    async def search(self, query: str, client: httpx.AsyncClient) -> list[Source]:
        async with self._lock:
            cached = self._cache.get(query)
            if cached is not None:
                logger.debug(f"[RESEARCH cache] '{query}' → {len(cached)}")
                return cached

        providers = ["OpenAlex"]
        tasks = [self.openalex.search(query, client)]
        if self.tavily and self.tavily.enabled:
            providers.append("Tavily")
            tasks.append(self.tavily.search(query, client))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        per_provider_counts: list[int] = []
        merged: list[Source] = []
        seen_ids: set[str] = set()
        for prov_name, res in zip(providers, results):
            if isinstance(res, Exception):
                logger.warning(f"[RESEARCH] {prov_name} відвалився: {res}")
                per_provider_counts.append(0)
                continue
            per_provider_counts.append(len(res))
            for s in res:
                if s.id in seen_ids:
                    continue
                seen_ids.add(s.id)
                merged.append(s)

        breakdown = ", ".join(
            f"{name}={count}" for name, count in zip(providers, per_provider_counts)
        )
        logger.info(f"[RESEARCH] '{query}' → {len(merged)} унік. ({breakdown})")

        async with self._lock:
            self._cache[query] = merged

        return merged
