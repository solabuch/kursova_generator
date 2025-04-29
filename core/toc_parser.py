# core/toc_parser.py
import re
import logging

logger = logging.getLogger(__name__)

def parse_toc(filepath: str) -> list[dict]:
    """
    Розбирає файл змісту з відступами.
    Повертає список словників, наприклад:
    [{'level': 0, 'number': 'ВСТУП', 'title': 'ВСТУП'},
     {'level': 0, 'number': 'РОЗДІЛ 1', 'title': 'ТЕОРЕТИЧНІ ОСНОВИ...'},
     {'level': 1, 'number': '1.1', 'title': 'Поняття та класифікація...'}, ...]
    """
    structure = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        logger.error(f"Файл змісту не знайдено: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Помилка читання файлу змісту {filepath}: {e}")
        raise

    section_counter = 0
    subsection_counters = {} # Для нумерації типу 1.1, 1.2, 2.1...

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'): # Пропускаємо порожні рядки та коментарі
            continue

        indent_level = (len(line) - len(line.lstrip(' '))) // 4 # Рахуємо рівень відступу (4 пробіли = 1 рівень)

        clean_title = line.lstrip(' ')
        number = clean_title # За замовчуванням номер = назва (для ВСТУП, ВИСНОВКИ)

        # Спробуємо визначити стандартну нумерацію (РОЗДІЛ N, X.Y)
        if indent_level == 0:
             match_section = re.match(r"РОЗДІЛ\s+(\d+)", clean_title, re.IGNORECASE)
             if match_section:
                 section_counter = int(match_section.group(1))
                 number = f"Розділ {section_counter}"
                 subsection_counters[section_counter] = 0 # Скидаємо лічильник підрозділів
             elif clean_title.upper() in ["ВСТУП", "ВИСНОВКИ ТА РЕКОМЕНДАЦІЇ", "ВИСНОВКИ", "СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ", "ДОДАТКИ"]:
                  number = clean_title.upper() # Використовуємо назву як "номер"
             else: # Якщо розділ не стандартний, використовуємо лічильник
                  section_counter += 1
                  number = f"Розділ {section_counter}"
                  subsection_counters[section_counter] = 0


        elif indent_level == 1 and section_counter > 0: # Підрозділ
            # Спробуємо знайти номер типу X.Y.
            match_subsection = re.match(r"(\d+\.\d+)\.?\s+", clean_title)
            if match_subsection:
                 number = match_subsection.group(1)
                 # Оновлюємо лічильник, щоб наступний авто-номер був правильним
                 try:
                     parts = number.split('.')
                     if len(parts) == 2:
                          sec_num, sub_num = int(parts[0]), int(parts[1])
                          if sec_num == section_counter:
                               subsection_counters[section_counter] = max(subsection_counters.get(section_counter, 0), sub_num)
                 except ValueError:
                     pass # Не вдалося розпарсити номер
            else: # Якщо номер не вказано явно, генеруємо автоматично
                subsection_counters[section_counter] = subsection_counters.get(section_counter, 0) + 1
                number = f"{section_counter}.{subsection_counters[section_counter]}"

        # Спробуємо видалити номер з початку назви, якщо він там є
        title_only = re.sub(r"^(РОЗДІЛ\s+\d+\.?|ВСТУП|ВИСНОВКИ|СПИСОК\s+.*|ДОДАТКИ|\d+(\.\d+)*\.?)\s*", "", clean_title, flags=re.IGNORECASE).strip()
        if not title_only: # Якщо після видалення нічого не лишилось, використовуємо повну назву
            title_only = clean_title


        structure.append({
            'level': indent_level,
            'number': number, # Номер (1.1, Розділ 2, ВСТУП)
            'title': title_only, # Назва без номера
            'full_title': clean_title # Повна назва з файлу
        })

    logger.info(f"Зміст успішно розібрано. Знайдено {len(structure)} пунктів.")
    return structure