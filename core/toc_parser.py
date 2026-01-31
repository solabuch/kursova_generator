# core/toc_parser.py
import re
import logging

logger = logging.getLogger(__name__)

def parse_lines(lines: list[str]) -> list[dict]:
    """
    Розбирає список рядків змісту.
    """
    structure = []
    section_counter = 0
    subsection_counters = {} 

    for raw_line in lines:
        # Спочатку рахуємо відступ
        if not raw_line.strip():
             continue
             
        indent_level = (len(raw_line) - len(raw_line.lstrip(' '))) // 4
        
        line = raw_line.strip()
        if line.startswith('#'): 
            continue

        clean_title = line.lstrip(' ')
        
        # Перевірка на X.Y (підрозділ), навіть якщо відступ 0
        if re.match(r"^\d+\.\d+", clean_title):
             indent_level = 1
             
        number = clean_title 

        # Спробуємо визначити стандартну нумерацію (РОЗДІЛ N, X.Y)
        if indent_level == 0:
             match_section = re.match(r"РОЗДІЛ\s+(\d+)", clean_title, re.IGNORECASE)
             if match_section:
                 section_counter = int(match_section.group(1))
                 number = f"Розділ {section_counter}"
                 subsection_counters[section_counter] = 0 
             elif clean_title.upper() in ["ВСТУП", "ВИСНОВКИ ТА РЕКОМЕНДАЦІЇ", "ВИСНОВКИ", "СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ", "ДОДАТКИ", "РЕЗЮМЕ"]:
                  number = clean_title.upper() 
             else: 
                  section_counter += 1
                  number = f"Розділ {section_counter}"
                  subsection_counters[section_counter] = 0

        elif indent_level == 1 and section_counter > 0: 
            match_subsection = re.match(r"(\d+\.\d+)\.?\s+", clean_title)
            if match_subsection:
                 number = match_subsection.group(1)
                 try:
                     parts = number.split('.')
                     if len(parts) == 2:
                          sec_num, sub_num = int(parts[0]), int(parts[1])
                          if sec_num == section_counter:
                               subsection_counters[section_counter] = max(subsection_counters.get(section_counter, 0), sub_num)
                 except ValueError:
                     pass 
            else: 
                subsection_counters[section_counter] = subsection_counters.get(section_counter, 0) + 1
                number = f"{section_counter}.{subsection_counters[section_counter]}"

        # Спробуємо видалити номер з початку назви
        title_only = re.sub(r"^(РОЗДІЛ\s+\d+\.?|ВСТУП|ВИСНОВКИ|СПИСОК\s+.*|ДОДАТКИ|\d+(\.\d+)*\.?)\s*", "", clean_title, flags=re.IGNORECASE).strip()
        if not title_only: 
            title_only = clean_title

        structure.append({
            'level': indent_level,
            'number': number, 
            'title': title_only, 
            'full_title': clean_title 
        })

    logger.info(f"Зміст успішно розібрано. Знайдено {len(structure)} пунктів.")
    return structure

def parse_toc(filepath: str) -> list[dict]:
    """
    Розбирає файл змісту з відступами.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return parse_lines(lines)
    except FileNotFoundError:
        logger.error(f"Файл змісту не знайдено: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Помилка читання файлу змісту {filepath}: {e}")
        raise