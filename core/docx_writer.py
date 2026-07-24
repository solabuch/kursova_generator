# core/docx_writer.py
"""Генерація DOCX за українськими академічними вимогами (ДСТУ).

Формат:
- A4, поля: ліве 3см, праве 1.5см, верх/низ 2см
- Times New Roman 14pt, міжрядковий інтервал 1.5
- Основний текст: ВИРІВНЮВАННЯ ПО ШИРИНІ, відступ першого рядка 1.25см
- Заголовки розділів (Heading 1): ВЕЛИКИМИ ЛІТЕРАМИ, центр, без відступу,
  кожен розділ починається з нової сторінки
- Заголовки підрозділів (Heading 2/3): звичайний регістр, ширина, 1.25см відступ
- Нумерація сторінок у верхньому колонтитулі (праворуч)
- Автоматичний зміст (поле TOC; у Word Ctrl+A → F9 для оновлення)
- Бібліографія — за ДСТУ 8302:2015
"""
import logging
import re
from datetime import date
from pathlib import Path
from typing import Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from core.dstu_formatter import build_bibliography
from core.models import GeneratedSection, Plan, SectionType, Source

logger = logging.getLogger(__name__)

TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
SEPARATOR_RE = re.compile(r"^\s*\|[\s:\|\-]+\|\s*$")
CITATION_RE = re.compile(r"\[(\d+)\]")
# Підпис таблиці від LLM: "[ТАБЛИЦЯ] Назва" (також толеруємо **[ТАБЛИЦЯ]** від Gemini)
TABLE_CAPTION_RE = re.compile(r"^\s*\*{0,2}\[ТАБЛИЦЯ\]\*{0,2}\s*(.+?)\s*$", re.IGNORECASE)

# Нормалізація під ДСТУ ГОСТ 7.1:2006 / методичку ЧДТУ:
# 1) Замінити em-dash (—) на en-dash (–) — між цифрами і у тире-як-розділі
# 2) Десятковий розділювач: крапка → кома (тільки в чистих числах, не у URL/DOI)
DASH_REPLACEMENTS = [("—", "–"), (" - ", " – ")]
DECIMAL_DOT_RE = re.compile(r"(?<![A-Za-z0-9./:_-])(\d+)\.(\d+)(?![/.A-Za-z0-9])")

# Markdown-розмітка, яку моделі (особливо Gemini) додають попри заборону у промпті
MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
MD_BOLD_ALT_RE = re.compile(r"__(.+?)__", re.DOTALL)
MD_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.DOTALL)
MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
# [N] посеред речення → переносимо в кінець абзацу (перед фінальною крапкою)
CITATION_MIDSENTENCE_RE = re.compile(r"\s*\[(\d+)\]\s*")


def strip_markdown(text: str) -> str:
    """Прибирає markdown-розмітку (**, __, *, #), яку моделі додають попри заборону."""
    text = MD_BOLD_RE.sub(r"\1", text)
    text = MD_BOLD_ALT_RE.sub(r"\1", text)
    text = MD_ITALIC_RE.sub(r"\1", text)
    text = MD_HEADING_RE.sub("", text)
    return text


def normalize_typography(text: str) -> str:
    """Виправляє типографіку згідно методички (en-dash, кома у числах) + прибирає markdown."""
    text = strip_markdown(text)
    for old, new in DASH_REPLACEMENTS:
        text = text.replace(old, new)
    text = DECIMAL_DOT_RE.sub(r"\1,\2", text)
    return text


def move_citations_to_paragraph_end(paragraph_text: str) -> str:
    """Переносить усі [N] у кінець абзацу (перед фінальною крапкою), без дублів, у порядку появи."""
    nums: list[str] = []
    for m in CITATION_MIDSENTENCE_RE.finditer(paragraph_text):
        if m.group(1) not in nums:
            nums.append(m.group(1))
    if not nums:
        return paragraph_text
    # Прибираємо всі [N] з тексту
    cleaned = CITATION_MIDSENTENCE_RE.sub(" ", paragraph_text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cites = "".join(f"[{n}]" for n in nums)
    # Ставимо перед фінальною крапкою/знаком
    if cleaned and cleaned[-1] in ".!?":
        return f"{cleaned[:-1].rstrip()} {cites}{cleaned[-1]}"
    return f"{cleaned} {cites}."

WORK_TYPE_LABELS = {
    "coursework": "КУРСОВА РОБОТА",
    "report": "ЗВІТ З ПРАКТИКИ",
    "essay": "РЕФЕРАТ",
    "diploma": "ДИПЛОМНА РОБОТА",
}


class DocxWriter:
    def __init__(
        self,
        plan: Plan,
        sections: list[GeneratedSection],
        bibliography: dict[str, Source],
        *,
        access_date: Optional[date] = None,
    ):
        self.plan = plan
        self.sections = sections
        self.access_date = access_date or date.today()
        self.doc = Document()

        # Нумерація таблиць: "Таблиця <розділ>.<порядковий>"
        self._current_chapter = 0
        self._table_seq = 0

        self._bib_formatted, self._id_to_global = build_bibliography(
            bibliography, access_date=self.access_date
        )

    def save(self, path: str | Path) -> Path:
        self._setup_document()
        self._add_title_page()

        # Page-break перед кожним level=0 (крім першого, після title page вже є).
        # Spacing logic між секціями:
        #   - parent-chapter (level=0 без body) → next subsection: 2 порожні рядки
        #   - subsection (level≥1) → next subsection: 1 порожній рядок
        #   - next.level == 0 → нічого (page break сам розділить)
        seen_first_chapter = False
        for i, section in enumerate(self.sections):
            if section.level == 0:
                if seen_first_chapter:
                    self.doc.add_page_break()
                seen_first_chapter = True

            self._add_section(section)

            nxt = self.sections[i + 1] if i + 1 < len(self.sections) else None
            if nxt is None or nxt.level == 0:
                continue
            if section.level == 0 and nxt.level > 0:
                self._blank_line()
                self._blank_line()
            elif section.level >= 1 and nxt.level >= 1:
                self._blank_line()

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(path))
        logger.info(f"DOCX збережено: {path}")
        return path

    # =========================== setup ===========================

    def _setup_document(self):
        # Поля сторінки за методичкою ЧДТУ: ліве 30мм, праве 10мм, верх/низ 20мм
        for section in self.doc.sections:
            section.top_margin = Cm(2)
            section.bottom_margin = Cm(2)
            section.left_margin = Cm(3)
            section.right_margin = Cm(1)

        # Усі стилі (body + heading): TNR 14pt, чорний, НЕ жирний, інтервал 1.5,
        # міжабзацного відступу НЕМАЄ. Heading-и існують лише для outline/TOC —
        # візуально не відрізняються від body, крім вирівнювання та відступу 1-го рядка.
        for name, indent_cm, alignment in (
            ("Normal", 1.25, WD_ALIGN_PARAGRAPH.JUSTIFY),
            ("Heading 1", 0, WD_ALIGN_PARAGRAPH.CENTER),
            ("Heading 2", 1.25, WD_ALIGN_PARAGRAPH.JUSTIFY),
            ("Heading 3", 1.25, WD_ALIGN_PARAGRAPH.JUSTIFY),
        ):
            self._configure_style(name, indent_cm=indent_cm, alignment=alignment)

        self._add_page_number_to_header()

    def _configure_style(
        self,
        name: str,
        *,
        indent_cm: float,
        alignment: int,
    ):
        """Уніфікований стиль: TNR 14pt, чорний, не жирний, 1.5 інтервал, 0 paragraph spacing."""
        style = self.doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(14)
        style.font.bold = False
        style.font.italic = False
        style.font.color.rgb = RGBColor(0, 0, 0)  # перекриває theme-color Word-a

        # Гарантуємо, що theme-атрибути кольору скинуті (інакше Heading може лишитись синім)
        rpr = style.element.get_or_add_rPr()
        color_el = rpr.find(qn("w:color"))
        if color_el is not None:
            for attr in ("w:themeColor", "w:themeShade", "w:themeTint"):
                if qn(attr) in color_el.attrib:
                    del color_el.attrib[qn(attr)]

        # rFonts — щоб Word не перескакував на інший шрифт на кирилиці.
        # ВАЖЛИВО: Heading 1/2/3 за замовчуванням мають themeAscii/themeHAnsi,
        # який має ВИЩИЙ пріоритет ніж w:ascii. Тому видаляємо theme-атрибути,
        # інакше заголовки рендеряться Calibri Light незалежно від w:ascii.
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        for theme_attr in (
            "w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme",
        ):
            if qn(theme_attr) in rfonts.attrib:
                del rfonts.attrib[qn(theme_attr)]
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), "Times New Roman")

        pf = style.paragraph_format
        pf.line_spacing = 1.5
        pf.first_line_indent = Cm(indent_cm)
        pf.alignment = alignment
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

    def _add_page_number_to_header(self):
        header = self.doc.sections[0].header
        paragraph = header.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph.paragraph_format.first_line_indent = Cm(0)
        self._insert_field(paragraph, "PAGE", placeholder="1")

    def _insert_field(self, paragraph, code: str, *, placeholder: str = ""):
        """Вставляє Word-поле (PAGE, TOC тощо)."""
        run = paragraph.add_run()
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = code
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        ph = OxmlElement("w:t")
        ph.text = placeholder
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        run._r.extend([fld_begin, instr, fld_sep, ph, fld_end])

    # ============================ pages ===========================

    def _add_title_page(self):
        label = WORK_TYPE_LABELS.get(self.plan.work_type, "КУРСОВА РОБОТА")

        for _ in range(5):
            self._blank_line()

        p = self.doc.add_paragraph(label)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(18)

        self._blank_line()
        self._blank_line()

        p = self.doc.add_paragraph(f"на тему: «{self.plan.topic}»")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)
        for r in p.runs:
            r.bold = True
            r.font.size = Pt(16)

        for _ in range(10):
            self._blank_line()

        p = self.doc.add_paragraph(str(date.today().year))
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.first_line_indent = Cm(0)

        self.doc.add_page_break()

    def _blank_line(self):
        p = self.doc.add_paragraph()
        p.paragraph_format.first_line_indent = Cm(0)

    # =========================== sections =========================

    def _add_section(self, section: GeneratedSection):
        # Відстеження поточного розділу для нумерації таблиць
        chap = self._extract_chapter_number(section)
        if chap is not None and chap != self._current_chapter:
            self._current_chapter = chap
            self._table_seq = 0

        heading = self._format_heading(section)
        style = self._heading_style_for(section.level)
        h = self.doc.add_paragraph(heading, style=style)

        # Defense-in-depth: ще раз форсуємо TNR на run-рівні (інколи стиль ігнорується).
        for run in h.runs:
            self._force_tnr_run(run)

        # Для рівня 0 явно обнуляємо відступ першого рядка
        if section.level == 0:
            h.paragraph_format.first_line_indent = Cm(0)
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Бібліографія: рендеримо справжній ДСТУ-список у цьому місці плану.
        if section.type == SectionType.BIBLIOGRAPHY:
            self._render_bibliography_list()
            return

        # Skip-секції (батько з нащадками) — тільки заголовок.
        if not section.content.strip():
            return

        # Порожній рядок між заголовком і тілом — для читабельності
        self._blank_line()

        remapped = self._remap_citations(section.content, section.sources)
        remapped = normalize_typography(remapped)
        self._add_body(remapped)

    def _render_bibliography_list(self):
        """ДСТУ 8302:2015 — нумерований список, кожен запис — як звичайний абзац (Normal style)."""
        if not self._bib_formatted:
            logger.warning("Бібліографія порожня — нема джерел, що реально процитовані у тексті")
            return
        for num, text, _src in self._bib_formatted:
            entry = normalize_typography(f"{num}. {text}")
            # Без override-ів: успадковує Normal (TNR 14, 1.5, JUSTIFY, 1.25см відступ).
            para = self.doc.add_paragraph(entry)
            for run in para.runs:
                self._force_tnr_run(run)

    def _force_tnr_run(self, run):
        """Гарантує TNR на рівні run-а, навіть якщо стиль успадкував theme-шрифт."""
        run.font.name = "Times New Roman"
        rpr = run._r.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.insert(0, rfonts)
        for theme_attr in (
            "w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme",
        ):
            if qn(theme_attr) in rfonts.attrib:
                del rfonts.attrib[qn(theme_attr)]
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rfonts.set(qn(attr), "Times New Roman")

    @staticmethod
    def _heading_style_for(level: int) -> str:
        if level == 0:
            return "Heading 1"
        if level == 1:
            return "Heading 2"
        return "Heading 3"

    @staticmethod
    def _format_heading(s: GeneratedSection) -> str:
        """
        Формати заголовків:
          ВСТУП, ВИСНОВКИ — повністю великими.
          level=0 "Розділ N ..." → "Розділ N НАЗВА" (слово 'Розділ' — як є, назва — великими).
          level≥1 "1.1 Назва підрозділу" — як у змісті.
        """
        if s.type == SectionType.INTRO:
            return "ВСТУП"
        if s.type == SectionType.CONCLUSION:
            return "ВИСНОВКИ"
        if s.level == 0:
            m = re.match(
                r"^\s*розділ\s+(\d+)[\.\s]+(.*)$",
                s.full_title,
                re.IGNORECASE,
            )
            if m:
                return f"Розділ {m.group(1)} {m.group(2).strip().upper()}"
            return s.full_title.strip().upper()
        return s.full_title.strip()

    def _remap_citations(self, content: str, section_sources: list[Source]) -> str:
        """Локальні [N] → глобальні [M] за ДСТУ. Невалідні — видаляємо."""
        def repl(m: re.Match) -> str:
            n = int(m.group(1))
            if 1 <= n <= len(section_sources):
                src = section_sources[n - 1]
                gnum = self._id_to_global.get(src.id)
                if gnum:
                    return f"[{gnum}]"
            return ""

        return CITATION_RE.sub(repl, content)

    def _add_body(self, content: str):
        blocks = re.split(r"\n\s*\n", content)
        pending_caption: str | None = None  # підпис [ТАБЛИЦЯ], що чекає на свою таблицю

        for block in blocks:
            lines = [ln.rstrip() for ln in block.split("\n") if ln.strip()]
            if not lines:
                continue

            i = 0
            while i < len(lines):
                # Рядок-підпис таблиці: "[ТАБЛИЦЯ] Назва"
                cap = TABLE_CAPTION_RE.match(lines[i])
                if cap:
                    pending_caption = cap.group(1).strip()
                    i += 1
                    continue

                if TABLE_LINE_RE.match(lines[i]):
                    j = i
                    while j < len(lines) and TABLE_LINE_RE.match(lines[j]):
                        j += 1
                    self._add_markdown_table(lines[i:j], caption=pending_caption)
                    pending_caption = None
                    i = j
                else:
                    j = i
                    while j < len(lines) and not TABLE_LINE_RE.match(lines[j]) \
                            and not TABLE_CAPTION_RE.match(lines[j]):
                        j += 1
                    text = " ".join(lines[i:j])
                    text = move_citations_to_paragraph_end(text)  # [N] у кінець абзацу
                    self.doc.add_paragraph(text)  # Normal → JUSTIFY + 1.25см
                    i = j

    def _add_markdown_table(self, lines: list[str], *, caption: str | None = None):
        rows: list[list[str]] = []
        for ln in lines:
            if SEPARATOR_RE.match(ln):
                continue
            cells = [strip_markdown(c.strip()) for c in ln.strip().strip("|").split("|")]
            rows.append(cells)
        if not rows:
            return

        # Підпис перед таблицею: "Таблиця N.M – Назва" (методичка ЧДТУ)
        self._blank_line()
        self._table_seq += 1
        chap = self._current_chapter or 1
        label = f"Таблиця {chap}.{self._table_seq}"
        caption_text = f"{label} – {caption}" if caption else label
        cap_para = self.doc.add_paragraph(caption_text)
        cap_para.paragraph_format.first_line_indent = Cm(0)
        cap_para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        for r in cap_para.runs:
            self._force_tnr_run(r)
            r.font.size = Pt(14)

        ncols = max(len(r) for r in rows)
        table = self.doc.add_table(rows=len(rows), cols=ncols)
        table.style = "Table Grid"

        for r_idx, row in enumerate(rows):
            for c_idx in range(ncols):
                cell = table.cell(r_idx, c_idx)
                cell.text = row[c_idx] if c_idx < len(row) else ""
                for p in cell.paragraphs:
                    p.paragraph_format.first_line_indent = Cm(0)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if r_idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
                    for r in p.runs:
                        # Методичка ЧДТУ: у таблицях БЕЗ жирного, кегль 12
                        r.font.name = "Times New Roman"
                        r.font.size = Pt(12)
                        r.bold = False

        self._blank_line()

    @staticmethod
    def _extract_chapter_number(section: GeneratedSection) -> int | None:
        """Витягує номер розділу для нумерації таблиць. '1.2'→1, 'Розділ 2'→2."""
        m = re.search(r"(\d+)", section.number or "")
        return int(m.group(1)) if m else None

