# core/file_handler.py
import os
import re
import logging

logger = logging.getLogger(__name__)

def sanitize_filename(name: str) -> str:
    """Видаляє або замінює символи, неприпустимі для імені файлу."""
    # Видаляємо номери типу "1.1.", "Розділ 1." на початку
    name = re.sub(r"^(Розділ\s*\d+\.?|\d+(\.\d+)*\.?)\s*", "", name)
    # Замінюємо пробіли та спецсимволи на підкреслення
    name = re.sub(r'[\\/*?:"<>|\s]+', '_', name)
    # Обмежуємо довжину (опціонально)
    return name[:100] # Обмеження довжини імені файлу

def save_content(output_dir: str, item: dict, content: str):
    """Зберігає згенерований контент у файл."""
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
            logger.info(f"Створено папку для результатів: {output_dir}")
        except OSError as e:
            logger.error(f"Не вдалося створити папку {output_dir}: {e}")
            return # Не можемо зберегти файл

    # Формуємо ім'я файлу: level_number_sanitized_title.txt
    # number може бути '1.1', 'Розділ 1', 'ВСТУП'
    number_part = str(item.get('number', 'unknown')).replace('.', '_').replace(' ', '_')
    filename_base = sanitize_filename(item.get('title', 'untitled'))
    filename = f"level{item.get('level', 0)}_{number_part}_{filename_base}.txt"
    filepath = os.path.join(output_dir, filename)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Збережено контент для '{item.get('full_title', 'N/A')}' у файл: {filepath}")
    except IOError as e:
        logger.error(f"Помилка запису у файл {filepath}: {e}")
    except Exception as e:
         logger.error(f"Неочікувана помилка при збереженні файлу {filepath}: {e}")