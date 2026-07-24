# main.py
"""CLI-точка входу для генератора академічних робіт v2.0."""
import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from ai_providers.openai_provider import OpenaiProvider
from core.docx_writer import DocxWriter
from core.models import GenerationState
from core.orchestrator import Orchestrator
from core.research import OpenAlexClient, ResearchAggregator, TavilyClient
from core.toc_parser import parse_toc

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    name = re.sub(r"^(Розділ\s*\d+\.?|\d+(\.\d+)*\.?)\s*", "", name)
    name = re.sub(r'[\\/*?:"<>|\s]+', "_", name)
    return name[:100].strip("_") or "output"


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    logger.info(f"Конфіг завантажено: {path}")
    return config


def _build_provider(config: dict, provider_name: str, model_override: str | None = None):
    pconf = dict(config["providers"][provider_name])  # копія, щоб не мутувати
    if model_override:
        pconf["model"] = model_override
    env_var = f"{provider_name.upper()}_API_KEY"
    api_key = pconf.get("api_key") or os.environ.get(env_var, "")
    if not api_key:
        raise ValueError(f"Немає API ключа для {provider_name} (config.api_key чи {env_var} у .env)")
    model = pconf["model"]
    if provider_name == "openai":
        return OpenaiProvider(api_key=api_key, model=model, config_params=pconf)
    if provider_name == "gemini":
        from ai_providers.gemini_provider import GeminiProvider
        return GeminiProvider(api_key=api_key, model=model, config_params=pconf)
    raise ValueError(f"Невідомий провайдер: {provider_name!r}")


def build_ai_provider(config: dict):
    """Legacy single-provider — використовується якщо немає preset."""
    name = config.get("active_provider", "openai")
    return _build_provider(config, name)


def build_providers_from_preset(config: dict, preset: str | None = None):
    """Повертає (main_provider, helper_provider) на основі обраного пресету."""
    preset = preset or config.get("default_preset", "standard")
    presets = config.get("presets") or {}
    spec = presets.get(preset)
    if not spec:
        logger.warning(f"Preset {preset!r} не знайдено — fallback на legacy single-provider")
        ai = build_ai_provider(config)
        return ai, ai
    main_spec = spec.get("main") or {}
    helper_spec = spec.get("helper") or main_spec
    main = _build_provider(config, main_spec["provider"], main_spec.get("model"))
    helper = _build_provider(config, helper_spec["provider"], helper_spec.get("model"))
    logger.info(
        f"Preset={preset!r}: main={main_spec['provider']}/{main.model}, "
        f"helper={helper_spec['provider']}/{helper.model}"
    )
    return main, helper


def build_orchestrator(config: dict, preset: str | None = None) -> Orchestrator:
    main, helper = build_providers_from_preset(config, preset)

    rconf = config.get("research", {}) or {}
    openalex = OpenAlexClient(
        email=rconf.get("openalex_email"),
        max_results=rconf.get("openalex_max_results", 8),
    )

    tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
    tavily = TavilyClient(api_key=tavily_key, max_results=5) if tavily_key else None
    if tavily:
        logger.info("Tavily: УВІМКНЕНО (pay-as-you-go web search)")

    aggregator = ResearchAggregator(openalex=openalex, tavily=tavily)

    ps = config.get("project_settings", {}) or {}
    return Orchestrator(
        ai=main,
        ai_helper=helper,
        research=aggregator,
        concurrency=ps.get("concurrency", 5),
        sources_per_section=ps.get("sources_per_section", 8),
    )


class CourseworkGenerator:
    """
    Sync-обгортка над async orchestrator + DocxWriter.
    Існує для backward-compat з web/app.py, який очікує саме цей API
    (config + log_callback на init, .run(...) повертає шлях).
    """

    def __init__(self, config: dict, log_callback=None):
        self.config = config
        # log_callback — legacy від v1; зараз web/app.py ловить логи через QueueHandler на root logger,
        # тож параметр ігноруємо. Лишаємо у сигнатурі для сумісності.
        self.log_callback = log_callback
        self.last_state: GenerationState | None = None  # для regenerate_section
        self._orchestrator: Orchestrator | None = None  # persistent для regen

    def run(
        self,
        topic: str,
        toc_text: str | None = None,
        input_toc_file: str | None = None,
        output_filename: str = "_final_course_paper.docx",
        overrides: dict | None = None,
        work_type: str = "coursework",
        methodology_text: str = "",
        section_types: list[str] | None = None,
        volume: str = "standard",
        preset: str | None = None,
    ) -> str:
        from core.toc_parser import parse_lines, parse_toc

        if toc_text:
            toc = parse_lines(toc_text.splitlines())
        elif input_toc_file:
            toc = parse_toc(input_toc_file)
        else:
            raise ValueError("Не вказано ні toc_text, ні input_toc_file")

        # Ручні перевизначення типу секції (з web UI). Зберігаємо у dict-ах TOC
        # під спецключем — orchestrator._classify їх читає.
        if section_types and len(section_types) == len(toc):
            applied = 0
            for it, override in zip(toc, section_types):
                if override and override != "auto":
                    it["_type_override"] = override
                    applied += 1
            if applied:
                logger.info(f"Ручних типів секцій: {applied}/{len(toc)}")
        elif section_types:
            logger.warning(
                f"section_types має довжину {len(section_types)}, а TOC — {len(toc)}. "
                f"Ігнорую перевизначення."
            )

        if overrides:
            logger.warning(
                f"overrides (manual section type) у v2.0 ще не підтримуються "
                f"({len(overrides)} перевизначень проігноровано)"
            )

        ps = self.config.get("project_settings", {}) or {}
        methodology = methodology_text or ps.get("methodology_summary", "")

        self._orchestrator = build_orchestrator(self.config, preset=preset)
        plan, sections, bibliography, research_pool, review = asyncio.run(
            self._orchestrator.run(
                toc,
                topic=topic,
                work_type=work_type,
                methodology=methodology,
                volume=volume,
            )
        )

        out_dir = Path(ps.get("output_dir", "output"))
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(output_filename).stem or sanitize_filename(topic)
        output_path = out_dir / f"{sanitize_filename(topic)}.docx" if stem.startswith("_final") else out_dir / f"{stem}.docx"

        writer = DocxWriter(plan=plan, sections=sections, bibliography=bibliography)
        writer.save(output_path)

        # Зберігаємо стан для можливої регенерації окремої секції
        self.last_state = GenerationState(
            plan=plan,
            sections=sections,
            research_pool=research_pool,
            bibliography=bibliography,
            output_path=str(output_path.resolve()),
            review=review,
        )
        return str(output_path.resolve())

    def regenerate_section(self, section_number: str, volume: str | None = None) -> str:
        """Перегенерує одну секцію зі збереженого стану та перезаписує .docx."""
        if not self.last_state or not self._orchestrator:
            raise RuntimeError("Немає попередньої генерації. Спершу запусти повну.")

        state = self.last_state
        new_section = asyncio.run(
            self._orchestrator.regenerate_section(
                state.plan,
                section_number,
                state.research_pool,
                state.sections,
                volume=volume,
            )
        )

        # Замінюємо секцію у списку, зберігаючи порядок
        updated = [new_section if g.number == section_number else g for g in state.sections]
        # Перебудовуємо бібліографію (могли з'явитись/зникнути цитати)
        new_bib = Orchestrator._build_bibliography(updated)

        # Перезаписуємо .docx
        out_path = Path(state.output_path)
        writer = DocxWriter(plan=state.plan, sections=updated, bibliography=new_bib)
        writer.save(out_path)

        # Оновлюємо state (review лишаємо з попереднього прогону)
        self.last_state = GenerationState(
            plan=state.plan,
            sections=updated,
            research_pool=state.research_pool,
            bibliography=new_bib,
            output_path=str(out_path.resolve()),
            review=state.review,
        )
        return str(out_path.resolve())


def load_methodology(path: str | None, fallback_text: str) -> str:
    if not path:
        return fallback_text
    p = Path(path)
    if not p.exists():
        logger.warning(f"Файл методички не знайдено: {p} — використовую fallback")
        return fallback_text
    suffix = p.suffix.lower()
    if suffix in (".txt", ".md"):
        return p.read_text(encoding="utf-8")
    logger.warning(
        f"Формат {suffix} не підтримується у MVP. Використовуйте .txt або .md."
    )
    return fallback_text


async def run_async(args: argparse.Namespace, config: dict) -> Path:
    ps = config.get("project_settings", {}) or {}

    topic: str = args.topic or ps.get("topic") or ""
    if not topic:
        raise ValueError("Тему не задано. Використайте --topic або вкажіть у config.yaml")

    work_type: str = args.work_type or ps.get("work_type", "coursework")
    toc_path: str = args.toc or ps.get("input_toc_file", "input/toc.txt")
    if not Path(toc_path).exists():
        raise FileNotFoundError(f"Файл змісту не знайдено: {toc_path}")

    methodology = load_methodology(args.methodology, ps.get("methodology_summary", ""))

    toc = parse_toc(toc_path)

    orchestrator = build_orchestrator(config)

    logger.info("=" * 60)
    logger.info(f"START | тема={topic!r} | тип={work_type} | секцій={len(toc)}")
    logger.info("=" * 60)

    plan, sections, bibliography, _research_pool, _review = await orchestrator.run(
        toc,
        topic=topic,
        work_type=work_type,
        methodology=methodology,
    )

    logger.info(
        f"Результат: {len(sections)} секцій згенеровано, "
        f"{len(bibliography)} унікальних джерел у бібліографії"
    )

    # Куди записати
    if args.output:
        output_path = Path(args.output)
    else:
        out_dir = Path(ps.get("output_dir", "output"))
        output_path = out_dir / f"{sanitize_filename(topic)}.docx"

    writer = DocxWriter(plan=plan, sections=sections, bibliography=bibliography)
    writer.save(output_path)

    logger.info("=" * 60)
    logger.info(f"✓ ГОТОВО: {output_path.resolve()}")
    logger.info("=" * 60)
    return output_path


def main() -> int:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Генератор академічних робіт v2.0 (async + OpenAlex + DOCX за ДСТУ)",
    )
    parser.add_argument("--config", default="config.yaml", help="Шлях до YAML-конфігу")
    parser.add_argument("--topic", help="Тема роботи (перевизначає config)")
    parser.add_argument("--toc", help="Шлях до файлу змісту (перевизначає config)")
    parser.add_argument(
        "--work-type",
        choices=["coursework", "report", "essay", "diploma"],
        help="Тип роботи",
    )
    parser.add_argument("--methodology", help="Шлях до .txt/.md методички")
    parser.add_argument("--output", help="Шлях до вихідного .docx файлу")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        asyncio.run(run_async(args, config))
        return 0
    except Exception as e:
        logger.error(f"Аварійне завершення: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
