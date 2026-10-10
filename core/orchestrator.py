# core/orchestrator.py
"""Асинхронний pipeline: план → розподіл тем → паралельний research → паралельна генерація body → intro/conclusions."""
import asyncio
import json
import logging
import re

import httpx

from ai_providers.base_provider import BaseAIProvider
from core.models import (
    ContentBlueprint,
    GeneratedSection,
    Plan,
    PlannedSection,
    ReviewIssue,
    SectionType,
    Source,
    WorkReview,
)
from core.prompts import (
    BLUEPRINT_BUILDER,
    DISTRIBUTOR,
    PLANNER,
    REGISTRY,
    REVIEWER,
    TRANSLATE_QUERIES,
    VOLUME_SPECS,
)
from core.research.aggregator import ResearchAggregator

logger = logging.getLogger(__name__)

BIBLIOGRAPHY_TITLE_HINTS = (
    "список використаних джерел",
    "список літератури",
    "література",
    "references",
    "bibliography",
)

CYRILLIC_RE = re.compile(r"[А-Яа-яЇїІіЄєҐґ]")


class Orchestrator:
    def __init__(
        self,
        ai: BaseAIProvider,
        research: ResearchAggregator,
        *,
        ai_helper: BaseAIProvider | None = None,
        concurrency: int = 5,
        sources_per_section: int = 8,
    ):
        self.ai = ai                                       # body theory/practical (preset)
        self.ai_helper = ai_helper or ai                   # planner/blueprint/translate/intro/conclusion
        self.research = research
        self.concurrency = concurrency
        self.sources_per_section = sources_per_section
        self._sem = asyncio.Semaphore(concurrency)
        self.volume: str = "standard"  # перезаписується у run()/regenerate_section()

    @property
    def volume_spec(self) -> str:
        return VOLUME_SPECS.get(self.volume, VOLUME_SPECS["standard"])

    # =========================== PLAN ===========================

    async def plan(
        self,
        toc: list[dict],
        *,
        topic: str,
        work_type: str,
        methodology: str,
    ) -> Plan:
        meth_len = len(methodology.strip()) if methodology else 0
        if meth_len:
            logger.info(f"ПЛАН: {len(toc)} секцій, тема={topic!r}, тип={work_type}, "
                        f"методичка={meth_len} символів ✓")
        else:
            logger.info(f"ПЛАН: {len(toc)} секцій, тема={topic!r}, тип={work_type}, "
                        f"методичка ВІДСУТНЯ")

        toc_text = "\n".join(f"{i['number']} {i['title']}" for i in toc)
        prompt = PLANNER.render(
            toc=toc_text,
            topic=topic,
            work_type=work_type,
            methodology=methodology,
        )

        raw = await self.ai_helper.generate(
            prompt,
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        plan_items = self._parse_plan_json(raw)
        if not plan_items:
            logger.warning(f"Planner повернув порожній JSON. RAW: {raw[:500]}")
        by_number = {item.get("number", ""): item for item in plan_items}

        sections: list[PlannedSection] = []
        for it in toc:
            enr = by_number.get(it["number"], {})
            stype = self._classify(it, enr)
            sections.append(
                PlannedSection(
                    number=it["number"],
                    title=it["title"],
                    full_title=it["full_title"],
                    level=it.get("level", 0),
                    type=stype,
                    guidance=enr.get("guidance", ""),
                    entities=enr.get("entities") or [],
                    research_query=enr.get("research_query") or it["title"],
                )
            )

        # Skip-логіка: батьки з нащадками + бібліографія
        self._mark_skip_generation(sections)

        logger.info(
            "План готовий: "
            + ", ".join(
                f"{s.number}[{s.type.value[:4]}{'⊘' if s.skip_generation else ''}]"
                for s in sections
            )
        )

        # F3: переклад research_query UA → EN
        await self._translate_queries_to_english(sections)

        return Plan(
            topic=topic,
            work_type=work_type,
            sections=sections,
            methodology=methodology,
        )

    @staticmethod
    def _parse_plan_json(raw: str) -> list[dict]:
        cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
            if not m:
                logger.error(f"Planner повернув не-JSON: {raw[:200]}")
                return []
            data = json.loads(m.group(0))
        if isinstance(data, dict):
            return data.get("sections") or data.get("plan") or []
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def _classify(it: dict, enr: dict) -> SectionType:
        # Ручний override з web UI має найвищий пріоритет
        override = it.get("_type_override")
        if override:
            try:
                return SectionType(override)
            except ValueError:
                logger.warning(f"Невалідний _type_override={override!r} — fallback на auto")

        title = it["full_title"].lower()
        if any(h in title for h in BIBLIOGRAPHY_TITLE_HINTS):
            return SectionType.BIBLIOGRAPHY
        if "вступ" in title or "резюме" in title:
            return SectionType.INTRO
        if "висновк" in title:
            return SectionType.CONCLUSION
        return (
            SectionType.PRACTICAL
            if enr.get("type") == "practical"
            else SectionType.THEORETICAL
        )

    @staticmethod
    def _mark_skip_generation(sections: list[PlannedSection]) -> None:
        """level=0 з нащадками → skip. BIBLIOGRAPHY → skip."""
        for i, sec in enumerate(sections):
            if sec.type == SectionType.BIBLIOGRAPHY:
                sec.skip_generation = True
                continue
            if sec.level == 0:
                # Чи є дитина (level>0) одразу після, до наступної level=0?
                for nxt in sections[i + 1 :]:
                    if nxt.level <= 0:
                        break
                    if nxt.level > 0:
                        sec.skip_generation = True
                        break

    async def _translate_queries_to_english(
        self,
        sections: list[PlannedSection],
    ) -> None:
        """Якщо research_query містить кирилицю — батч-переклад на EN одним LLM-call."""
        needs: list[PlannedSection] = [
            s for s in sections
            if not s.skip_generation
            and s.research_query
            and CYRILLIC_RE.search(s.research_query)
        ]
        if not needs:
            return

        prompt = TRANSLATE_QUERIES.render(queries=[s.research_query for s in needs])
        try:
            raw = await self.ai_helper.generate(
                prompt,
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            data = json.loads(raw)
            translated = data.get("queries") or []
        except Exception as e:
            logger.warning(f"Не вдалося перекласти queries: {e}")
            return

        for sec, eng in zip(needs, translated):
            if eng and isinstance(eng, str):
                logger.info(f"Translate [{sec.number}]: {sec.research_query!r} → {eng!r}")
                sec.research_query = eng

    # ========================= DISTRIBUTE TOPICS =========================

    async def build_blueprints(self, plan: Plan) -> None:
        """Pre-generation: LLM створює глибокий content blueprint для кожної body-секції.
        Це замінює простий cover/avoid — кожна секція отримує main_thesis, key_subtopics,
        must_define, facts_to_find (що підкріпити джерелами), depth_focus."""
        targets = [s for s in plan.sections if self._needs_content(s)
                   and s.type in (SectionType.THEORETICAL, SectionType.PRACTICAL)]
        if not targets:
            return

        toc_text = "\n".join(f"{s.number} {s.full_title}" for s in targets)
        prompt = BLUEPRINT_BUILDER.render(
            topic=plan.topic,
            work_type=plan.work_type,
            methodology=plan.methodology,
            toc=toc_text,
        )

        try:
            raw = await self.ai_helper.generate(
                prompt,
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=8000,
            )
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"Blueprint generation failed: {e}")
            return

        blueprints = data.get("blueprints") or data.get("distribution") or {}
        applied = 0
        for sec in targets:
            entry = blueprints.get(sec.number)
            if not entry:
                continue
            try:
                # Підтримка legacy формату {cover, avoid}
                if "cover" in entry and "main_thesis" not in entry:
                    sec.cover_topics = list(entry.get("cover") or [])
                    sec.avoid_topics = list(entry.get("avoid") or [])
                else:
                    sec.blueprint = ContentBlueprint(
                        main_thesis=str(entry.get("main_thesis", "")),
                        key_subtopics=list(entry.get("key_subtopics") or []),
                        must_define=list(entry.get("must_define") or []),
                        facts_to_find=list(entry.get("facts_to_find") or []),
                        depth_focus=str(entry.get("depth_focus", "")),
                        avoid_overlap_with=[str(x) for x in (entry.get("avoid_overlap_with") or [])],
                    )
                applied += 1
            except Exception as e:
                logger.warning(f"Blueprint для {sec.number} некоректний: {e}")

        logger.info(f"BLUEPRINTS: побудовано для {applied}/{len(targets)} секцій")

    # Backward-compat alias
    distribute_topics = build_blueprints

    @staticmethod
    def _needs_content(s: PlannedSection) -> bool:
        """Чи треба генерувати LLM-контент для секції."""
        return (
            not s.skip_generation
            and s.type in (
                SectionType.THEORETICAL,
                SectionType.PRACTICAL,
                SectionType.INTRO,
                SectionType.CONCLUSION,
            )
        )

    # =========================== RESEARCH ===========================

    async def gather_research(
        self,
        plan: Plan,
        client: httpx.AsyncClient,
    ) -> dict[str, list[Source]]:
        targets = [
            s for s in plan.sections
            if not s.skip_generation
            and s.type in (SectionType.THEORETICAL, SectionType.PRACTICAL)
        ]
        logger.info(f"RESEARCH: {len(targets)} паралельних запитів")

        async def _one(sec: PlannedSection) -> tuple[str, list[Source]]:
            query = sec.research_query or sec.title
            sources = await self.research.search(query, client)
            return sec.number, sources[: self.sources_per_section]

        results = await asyncio.gather(*(_one(s) for s in targets))
        pool = dict(results)
        total = sum(len(v) for v in pool.values())
        logger.info(f"RESEARCH: зібрано {total} джерел для {len(pool)} секцій")
        return pool

    # =========================== GENERATE ===========================

    async def generate(
        self,
        plan: Plan,
        research_pool: dict[str, list[Source]],
    ) -> list[GeneratedSection]:
        body = [
            s for s in plan.sections
            if not s.skip_generation
            and s.type in (SectionType.THEORETICAL, SectionType.PRACTICAL)
        ]
        logger.info(
            f"GENERATE body: {len(body)} секцій паралельно (concurrency={self.concurrency})"
        )

        body_results: list[GeneratedSection] = await asyncio.gather(
            *[
                self._gen_section(
                    sec,
                    plan,
                    sources=research_pool.get(sec.number, []),
                    body_context="",
                )
                for sec in body
            ]
        )

        # Контекст для вступу/висновків — abstracts у порядку плану
        order = {s.number: i for i, s in enumerate(plan.sections)}
        body_results.sort(key=lambda g: order[g.number])
        body_context = "\n\n".join(
            f"{g.full_title}: {g.abstract}" for g in body_results
        )

        frame = [
            s for s in plan.sections
            if not s.skip_generation
            and s.type in (SectionType.INTRO, SectionType.CONCLUSION)
        ]
        frame_results: list[GeneratedSection] = []
        for sec in frame:  # sequential — мало й залежать від body
            frame_results.append(
                await self._gen_section(sec, plan, sources=[], body_context=body_context)
            )

        # Skip-секції — заглушки тільки з заголовком, без content
        skipped_results: list[GeneratedSection] = [
            GeneratedSection(
                number=sec.number,
                full_title=sec.full_title,
                level=sec.level,
                type=sec.type,
                content="",
                sources=[],
                used_source_ids=[],
                abstract="",
            )
            for sec in plan.sections if sec.skip_generation
        ]

        # Строге відновлення порядку плану
        plan_index = {s.number: i for i, s in enumerate(plan.sections)}
        all_results = body_results + frame_results + skipped_results
        all_results.sort(key=lambda g: plan_index.get(g.number, 10**9))

        missing = [
            s.number for s in plan.sections
            if s.number not in {g.number for g in all_results}
        ]
        if missing:
            logger.warning(f"Не згенеровано секцій: {missing}")

        return all_results

    async def _gen_section(
        self,
        sec: PlannedSection,
        plan: Plan,
        *,
        sources: list[Source],
        body_context: str,
    ) -> GeneratedSection:
        template = REGISTRY[sec.type.value]

        prompt = template.render(
            topic=plan.topic,
            work_type=plan.work_type,
            section=sec,
            sources=sources,
            methodology=plan.methodology,
            body_context=body_context,
            volume_spec=self.volume_spec,
        )

        # Body theory/practical → main модель (preset). Intro/Conclusion → helper.
        provider = self.ai if sec.type in (SectionType.THEORETICAL, SectionType.PRACTICAL) else self.ai_helper
        async with self._sem:
            logger.info(f"→ GEN [{sec.type.value}] {sec.full_title} | {provider.__class__.__name__}")
            try:
                content = await provider.generate(prompt, temperature=0.7)
            except Exception as e:
                logger.error(f"✗ GEN FAIL [{sec.full_title}]: {e}")
                content = (
                    f"[ПОМИЛКА ГЕНЕРАЦІЇ]\nРозділ: {sec.full_title}\nПричина: {e}"
                )

        content = self._strip_duplicate_heading(content, sec)
        abstract = self._extract_abstract(content)
        used_ids = self._detect_used_sources(content, sources)

        logger.info(
            f"✓ GEN [{sec.full_title}] {len(content)} chars, "
            f"цитат={len(used_ids)}/{len(sources)}"
        )
        return GeneratedSection(
            number=sec.number,
            full_title=sec.full_title,
            level=sec.level,
            type=sec.type,
            content=content,
            sources=sources,
            used_source_ids=used_ids,
            abstract=abstract,
        )

    # =========================== RUN ===========================

    async def run(
        self,
        toc: list[dict],
        *,
        topic: str,
        work_type: str = "coursework",
        methodology: str = "",
        volume: str = "standard",
        review: bool = True,
    ) -> tuple[Plan, list[GeneratedSection], dict[str, Source], dict[str, list[Source]], "WorkReview | None"]:
        """Повний pipeline. Повертає (plan, sections, bibliography, research_pool, review)."""
        self.volume = volume
        async with httpx.AsyncClient(
            headers={"User-Agent": "kursova-generator/2.0"}
        ) as client:
            plan = await self.plan(
                toc,
                topic=topic,
                work_type=work_type,
                methodology=methodology,
            )
            plan.volume = volume
            await self.build_blueprints(plan)
            research_pool = await self.gather_research(plan, client)
            sections = await self.generate(plan, research_pool)

        bibliography = self._build_bibliography(sections)

        work_review = None
        if review:
            work_review = await self.review_work(plan, sections, bibliography)

        return plan, sections, bibliography, research_pool, work_review

    # =========================== REVIEW ===========================

    async def review_work(
        self,
        plan: Plan,
        sections: list[GeneratedSection],
        bibliography: dict[str, Source],
    ) -> "WorkReview | None":
        """Фінальний LLM-проxід: оцінка цілісності + рекомендації що перегенерувати."""
        body = [s for s in sections if s.content.strip()
                and s.type in (SectionType.THEORETICAL, SectionType.PRACTICAL,
                               SectionType.INTRO, SectionType.CONCLUSION)]
        if not body:
            return None

        # Дайджест: заголовок + перші ~500 символів кожної секції
        digest_parts = []
        for g in body:
            snippet = g.content.strip().replace("\n", " ")[:500]
            digest_parts.append(f"[{g.number}] {g.full_title}\n{snippet}...")
        digest = "\n\n".join(digest_parts)

        prompt = REVIEWER.render(
            topic=plan.topic,
            work_type=plan.work_type,
            sections_digest=digest,
            sources_count=len(bibliography),
        )
        logger.info("REVIEW: запуск фінальної рецензії...")
        try:
            raw = await self.ai_helper.generate(
                prompt,
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=2000,
            )
            data = json.loads(raw)
            issues = [
                ReviewIssue(
                    section=str(it.get("section", "")),
                    problem=str(it.get("problem", "")),
                    severity=it.get("severity", "medium")
                    if it.get("severity") in ("low", "medium", "high") else "medium",
                )
                for it in (data.get("issues") or [])
            ]
            review = WorkReview(
                score=float(data.get("score", 0) or 0),
                verdict=str(data.get("verdict", "")),
                strengths=[str(x) for x in (data.get("strengths") or [])],
                issues=issues,
                regenerate_recommended=[str(x) for x in (data.get("regenerate_recommended") or [])],
            )
            logger.info(f"REVIEW: оцінка {review.score}/10, проблем: {len(review.issues)}")
            return review
        except Exception as e:
            logger.warning(f"REVIEW: не вдалося — {e}")
            return None

    async def regenerate_section(
        self,
        plan: Plan,
        section_number: str,
        research_pool: dict[str, list[Source]],
        existing_sections: list[GeneratedSection],
        *,
        volume: str | None = None,
    ) -> GeneratedSection:
        """Перегенерує одну секцію без перезапуску усього pipeline."""
        sec = next((s for s in plan.sections if s.number == section_number), None)
        if not sec:
            raise ValueError(f"Секція {section_number!r} не знайдена у плані")
        if sec.skip_generation:
            raise ValueError(f"Секція {section_number!r} — пропускається (батько з нащадками або BIBLIOGRAPHY)")

        self.volume = volume or plan.volume or "standard"

        # Контекст для intro/conclusion — abstracts інших body-секцій
        if sec.type in (SectionType.INTRO, SectionType.CONCLUSION):
            body_context = "\n\n".join(
                f"{g.full_title}: {g.abstract}"
                for g in existing_sections
                if g.type in (SectionType.THEORETICAL, SectionType.PRACTICAL)
                and g.number != section_number
            )
        else:
            body_context = ""

        sources = research_pool.get(section_number, [])
        logger.info(f"REGEN [{sec.type.value}] {sec.full_title} (volume={self.volume})")
        return await self._gen_section(
            sec, plan, sources=sources, body_context=body_context
        )

    @staticmethod
    def _build_bibliography(sections: list[GeneratedSection]) -> dict[str, Source]:
        """Тільки джерела, що реально процитовані хоча б в одній секції."""
        used: set[str] = set()
        for g in sections:
            used.update(g.used_source_ids)

        bib: dict[str, Source] = {}
        for g in sections:
            for s in g.sources:
                if s.id in used and s.id not in bib:
                    bib[s.id] = s
        return bib

    # =========================== helpers ===========================

    @staticmethod
    def _strip_duplicate_heading(text: str, sec: PlannedSection) -> str:
        lines = text.split("\n")
        if not lines:
            return text
        first = lines[0].strip().lower()
        looks_like_heading = (
            sec.title.lower() in first
            or re.match(r"^(розділ|\d+\.\d*\s|вступ|висновк)", first)
        )
        if looks_like_heading:
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
        return "\n".join(lines).strip()

    @staticmethod
    def _extract_abstract(content: str, max_chars: int = 400) -> str:
        para = content.strip().split("\n\n", 1)[0]
        return para[:max_chars].strip()

    @staticmethod
    def _detect_used_sources(
        content: str,
        sources: list[Source],
    ) -> list[str]:
        """Маппінг локальних [N] → Source.id. Невідомі номери ігноруємо."""
        found: set[int] = {int(m.group(1)) for m in re.finditer(r"\[(\d+)\]", content)}
        ids: list[str] = []
        for n in sorted(found):
            if 1 <= n <= len(sources):
                ids.append(sources[n - 1].id)
        return ids
