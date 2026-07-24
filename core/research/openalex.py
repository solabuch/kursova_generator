# core/research/openalex.py
"""OpenAlex — безкоштовний API на 250M+ наукових робіт."""
import hashlib
import logging
from typing import Optional

import httpx

from core.models import Source

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"


class OpenAlexClient:
    def __init__(self, email: Optional[str] = None, max_results: int = 8):
        # email переводить запити у polite pool — швидше та стабільніше
        self.email = email
        self.max_results = max_results

    async def search(self, query: str, client: httpx.AsyncClient) -> list[Source]:
        params = {
            "search": query,
            "per-page": self.max_results,
            "select": (
                "id,doi,title,authorships,publication_year,"
                "primary_location,abstract_inverted_index,biblio,type"
            ),
        }
        if self.email:
            params["mailto"] = self.email

        try:
            r = await client.get(f"{OPENALEX_BASE}/works", params=params, timeout=20.0)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            logger.warning(f"OpenAlex error для '{query}': {e}")
            return []

        sources = [self._parse_work(w) for w in data.get("results", [])]
        logger.info(f"OpenAlex: '{query}' → {len(sources)} джерел")
        return sources

    def _parse_work(self, w: dict) -> Source:
        doi_raw = w.get("doi")
        doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

        authors = [
            a["author"]["display_name"]
            for a in (w.get("authorships") or [])[:5]
            if a.get("author")
        ]

        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        biblio = w.get("biblio") or {}

        abstract = self._inverted_to_text(w.get("abstract_inverted_index"))

        openalex_id = w.get("id", "")
        sid = doi or hashlib.md5(openalex_id.encode()).hexdigest()[:12]

        pages = None
        fp, lp = biblio.get("first_page"), biblio.get("last_page")
        if fp and lp:
            pages = f"{fp}-{lp}"
        elif fp:
            pages = str(fp)

        stype = "article" if w.get("type") == "article" else "proceedings"

        return Source(
            id=sid,
            authors=authors,
            title=w.get("title") or "Без назви",
            year=w.get("publication_year"),
            source_type=stype,
            journal=src.get("display_name"),
            volume=biblio.get("volume"),
            issue=biblio.get("issue"),
            pages=pages,
            doi=doi,
            url=openalex_id or None,
            abstract=abstract[:500] if abstract else None,
        )

    @staticmethod
    def _inverted_to_text(inv: Optional[dict]) -> Optional[str]:
        """OpenAlex віддає abstract як {word: [positions]}. Відновлюємо порядок."""
        if not inv:
            return None
        positions: list[tuple[int, str]] = []
        for word, idx_list in inv.items():
            for i in idx_list:
                positions.append((i, word))
        positions.sort()
        return " ".join(w for _, w in positions)
