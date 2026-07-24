# core/dstu_formatter.py
"""Форматер бібліографії за ДСТУ 8302:2015."""
import re
from datetime import date
from typing import Optional

from core.models import Source

CYRILLIC_RE = re.compile(r"[А-Яа-яЇїІіЄєҐґ]")


def _is_cyrillic(text: str) -> bool:
    return bool(CYRILLIC_RE.search(text))


def _format_author(name: str) -> str:
    """'Ivan Ivanenko' → 'Ivanenko I.'; 'Іван Петрович Іваненко' → 'Іваненко І. П.'"""
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    surname = parts[-1]
    initials = " ".join(f"{p[0]}." for p in parts[:-1])
    return f"{surname} {initials}"


def _authors_block(authors: list[str], max_before_etal: int = 3) -> str:
    if not authors:
        return ""
    if len(authors) <= max_before_etal:
        return ", ".join(_format_author(a) for a in authors if a)
    return f"{_format_author(authors[0])} та ін."


def format_source(src: Source, access_date: Optional[date] = None) -> str:
    """Один запис бібліографії за ДСТУ 8302:2015."""
    access_date = access_date or date.today()
    if src.source_type == "book":
        return _format_book(src)
    if src.source_type == "web":
        return _format_web(src, access_date)
    return _format_article(src)


def _format_article(s: Source) -> str:
    """Прізвище І. І. Назва статті. Журнал. 2023. Т. 5, № 2. С. 10–15. DOI: ..."""
    parts: list[str] = []
    authors = _authors_block(s.authors)
    if authors:
        parts.append(authors)
    parts.append(s.title.rstrip("."))
    if s.journal:
        parts.append(s.journal)
    if s.year:
        parts.append(str(s.year))

    vol_issue: list[str] = []
    if s.volume:
        vol_issue.append(f"Т. {s.volume}")
    if s.issue:
        vol_issue.append(f"№ {s.issue}")
    if vol_issue:
        parts.append(", ".join(vol_issue))

    if s.pages:
        parts.append(f"С. {s.pages.replace('-', '–').replace('—', '–')}")
    if s.doi:
        parts.append(f"DOI: {s.doi}")

    return ". ".join(p.rstrip(".").strip() for p in parts if p) + "."


def _format_book(s: Source) -> str:
    """Прізвище І. І. Назва книги. Київ : Видавництво, 2023. 250 с."""
    parts: list[str] = []
    authors = _authors_block(s.authors)
    if authors:
        parts.append(authors)
    parts.append(s.title.rstrip("."))

    imprint_bits: list[str] = []
    if s.city:
        imprint_bits.append(s.city)
    if s.publisher:
        imprint_bits.append(s.publisher)

    if imprint_bits and s.year:
        parts.append(f"{' : '.join(imprint_bits)}, {s.year}")
    elif imprint_bits:
        parts.append(" : ".join(imprint_bits))
    elif s.year:
        parts.append(str(s.year))

    if s.pages:
        parts.append(f"{s.pages} с")

    return ". ".join(p.rstrip(".").strip() for p in parts if p) + "."


def _format_web(s: Source, access_date: date) -> str:
    """Прізвище І. І. Назва. URL: ... (дата звернення: 20.04.2026)."""
    authors = _authors_block(s.authors)
    title = s.title.rstrip(".")
    url = s.url or ""
    dstr = access_date.strftime("%d.%m.%Y")
    tail = f"URL: {url} (дата звернення: {dstr})"
    if authors:
        return f"{authors}. {title}. {tail}."
    return f"{title}. {tail}."


def build_bibliography(
    sources: dict[str, Source],
    access_date: Optional[date] = None,
) -> tuple[list[tuple[int, str, Source]], dict[str, int]]:
    """
    Сортує та нумерує бібліографію. ДСТУ: кирилиця → латиниця, за прізвищем/назвою.

    Повертає:
      formatted — [(глобальний_номер, текст_за_ДСТУ, Source), ...]
      id_to_num — {Source.id: глобальний_номер}
    """
    items = list(sources.values())

    def sort_key(s: Source) -> tuple[int, str]:
        anchor = (s.authors[0] if s.authors else s.title) or ""
        alphabet_rank = 0 if _is_cyrillic(anchor) else 1
        return (alphabet_rank, anchor.lower())

    items.sort(key=sort_key)
    formatted = [
        (i + 1, format_source(s, access_date=access_date), s)
        for i, s in enumerate(items)
    ]
    id_to_num = {s.id: i + 1 for i, s in enumerate(items)}
    return formatted, id_to_num
