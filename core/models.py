# core/models.py
"""Pydantic-моделі домену: джерела, секції, план."""
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class SectionType(str, Enum):
    THEORETICAL = "theoretical"
    PRACTICAL = "practical"
    INTRO = "intro"
    CONCLUSION = "conclusion"
    BIBLIOGRAPHY = "bibliography"  # СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ — не генеруємо, лишаємо плейсхолдер


class Source(BaseModel):
    """Джерело для бібліографії ДСТУ 8302:2015."""
    id: str  # DOI або md5-хеш
    authors: list[str] = Field(default_factory=list)
    title: str
    year: Optional[int] = None
    source_type: Literal["article", "book", "web", "proceedings"] = "article"
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    city: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    abstract: Optional[str] = None

    @property
    def first_author_surname(self) -> str:
        if not self.authors:
            return "Анонім"
        # "Ivan Ivanenko" -> "Ivanenko"; "Іваненко І.І." -> "Іваненко"
        name = self.authors[0].strip()
        parts = name.split()
        return parts[-1] if len(parts) > 1 and len(parts[-1]) > 2 else parts[0]


class ContentBlueprint(BaseModel):
    """Глибокий JSON-план що писати у конкретній секції.
    `outline` — нова детальна послідовність 8-15 пунктів, які writer LLM розкриває по черзі.
    `key_subtopics` лишається для backward-compat."""
    main_thesis: str = ""                  # головна теза підрозділу (1 речення)
    outline: list[str] = Field(default_factory=list)         # NEW: 8-15 деталних пунктів-завдань
    key_subtopics: list[str] = Field(default_factory=list)   # legacy
    must_define: list[str] = Field(default_factory=list)     # терміни, що мають отримати визначення
    facts_to_find: list[str] = Field(default_factory=list)   # що варто знайти в джерелах (без вигаданих значень)
    depth_focus: str = ""                  # на чому копаємо глибше
    avoid_overlap_with: list[str] = Field(default_factory=list)  # номери інших секцій


class PlannedSection(BaseModel):
    number: str
    title: str
    full_title: str
    level: int
    type: SectionType
    guidance: str = ""
    entities: list[str] = Field(default_factory=list)
    research_query: Optional[str] = None
    skip_generation: bool = False  # True для level=0 з нащадками + BIBLIOGRAPHY
    # Legacy — лишаємо для backward-compat зі старими промптами
    cover_topics: list[str] = Field(default_factory=list)
    avoid_topics: list[str] = Field(default_factory=list)
    # Новий механізм — глибокий JSON план
    blueprint: Optional[ContentBlueprint] = None


class GeneratedSection(BaseModel):
    number: str
    full_title: str
    level: int
    type: SectionType
    content: str
    sources: list[Source] = Field(default_factory=list)  # локальний порядок [1..N] у тексті
    used_source_ids: list[str] = Field(default_factory=list)
    abstract: str = ""  # короткий opener для контексту intro/conclusion


class Plan(BaseModel):
    topic: str
    work_type: str
    sections: list[PlannedSection]
    methodology: str = ""
    volume: str = "standard"  # short | standard | detailed


class ReviewIssue(BaseModel):
    section: str = ""
    problem: str = ""
    severity: Literal["low", "medium", "high"] = "medium"


class WorkReview(BaseModel):
    """Рецензія ШІ на готову роботу."""
    score: float = 0.0
    verdict: str = ""
    strengths: list[str] = Field(default_factory=list)
    issues: list[ReviewIssue] = Field(default_factory=list)
    regenerate_recommended: list[str] = Field(default_factory=list)


class GenerationState(BaseModel):
    """Стан останньої генерації — потрібен для регенерації окремої секції."""
    plan: Plan
    sections: list[GeneratedSection]
    research_pool: dict[str, list[Source]]
    bibliography: dict[str, Source]
    output_path: str
    review: Optional[WorkReview] = None
