
# main.py
import yaml
import importlib
import logging
import os
import argparse
from typing import List, Dict, Callable, Optional
from dotenv import load_dotenv

# Завантажуємо змінні середовища з .env файлу
load_dotenv()

# Імпортуємо потрібні модулі з нашого проєкту
from core.toc_parser import parse_toc, parse_lines
from core.file_handler import save_content, sanitize_filename
from core.orchestrator import Orchestrator 
from ai_providers.base_provider import BaseAIProvider

# Налаштування логування
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    """Завантажує конфігурацію з YAML файлу."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Конфігурацію завантажено з {config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"Файл конфігурації не знайдено: {config_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Помилка читання YAML файлу {config_path}: {e}")
        raise
    except Exception as e:
         logger.error(f"Загальна помилка при завантаженні конфігурації: {e}")
         raise

def get_ai_provider(config: dict) -> BaseAIProvider:
    """Створює екземпляр відповідного AI провайдера на основі конфігурації."""
    provider_name = config.get('active_provider')
    if not provider_name:
        raise ValueError("Не вказано 'active_provider' у конфігурації.")

    provider_config = config.get('providers', {}).get(provider_name)
    if not provider_config:
        raise ValueError(f"Конфігурація для провайдера '{provider_name}' не знайдена.")

    api_key = provider_config.get('api_key')
    model = provider_config.get('model')
    config_params = provider_config 

    if not api_key:
         api_key_env_var = f"{provider_name.upper()}_API_KEY" 
         api_key = os.environ.get(api_key_env_var)
         if not api_key:
              logger.warning(f"API ключ для {provider_name} не знайдено ні в config.yaml, ні в змінній середовища {api_key_env_var}.")

    if not model:
        raise ValueError(f"Не вказано 'model' для провайдера '{provider_name}' у конфігурації.")

    try:
        module_path = f"ai_providers.{provider_name}_provider"
        provider_module = importlib.import_module(module_path)
        class_name = f"{provider_name.capitalize()}Provider"
        ProviderClass = getattr(provider_module, class_name)
        instance = ProviderClass(api_key=api_key, model=model, config_params=config_params)
        logger.info(f"Створено екземпляр AI провайдера: {class_name} з моделлю {model}")
        return instance

    except Exception as e:
         logger.error(f"Помилка при створенні AI провайдера {provider_name}: {e}")
         raise

def combine_output_files(output_dir: str, final_filename: str, structure: list[dict], topic: str):
    """
    Об'єднує згенеровані файли в один фінальний файл.
    Джерела сортуються за алфавітом, посилання перенумеровуються відповідно.
    """
    import re
    
    final_filepath = os.path.join(output_dir, final_filename)
    sources_filepath = os.path.join(output_dir, "_sources.txt")
    logger.info(f"Початок об'єднання файлів у: {final_filepath}")

    source_block_re = re.compile(r'\[\[SOURCE_LIST\]\](.*?)\[\[/SOURCE_LIST\]\]', re.DOTALL)
    citation_re = re.compile(r'\[(\d+)\]')

    # ===== PASS 1: Збираємо всі джерела та контент =====
    all_sources_set = set()  # Унікальні джерела
    sections_data = []       # Список: {'header': str, 'content': str, 'local_sources': list}

    for item in structure:
        number_part = str(item.get('number', 'unknown')).replace('.', '_').replace(' ', '_')
        filename_base = sanitize_filename(item.get('title', 'untitled'))
        individual_filename = f"level{item.get('level', 0)}_{number_part}_{filename_base}.txt"
        individual_filepath = os.path.join(output_dir, individual_filename)

        # ЗАГОЛОВОК
        level = item.get('level', 0)
        number = item.get('number')
        title = item.get('title', 'Без назви')

        if number:
            if level == 0:
                clean_num = str(number).lower().replace('розділ', '').strip()
                if clean_num and clean_num[0].isdigit():
                    # Формат: "Розділ 1 НАЗВА" (Розділ з великої, назва капсом)
                    header_title = f"Розділ {clean_num} {title.upper()}"
                else:
                    if title.upper() in ["ВСТУП", "ВИСНОВКИ", "РЕЗЮМЕ"]:
                        header_title = title.upper()
                    else:
                        header_title = f"{number} {title.upper()}"
            else:
                header_title = f"{number} {title}"
        else:
            header_title = title.upper()
        
        # Пропускаємо секцію джерел
        if "список використаних джерел" in header_title.lower() or "список літератури" in header_title.lower():
            continue

        section_entry = {'header': header_title, 'content': '', 'local_sources': []}

        if os.path.exists(individual_filepath):
            try:
                with open(individual_filepath, 'r', encoding='utf-8') as infile:
                    content = infile.read()
                
                # Функція нормалізації джерел (видаляє зайві пробіли, уніфікує формат)
                def normalize_source(s: str) -> str:
                    # Видаляємо подвійні пробіли
                    s = re.sub(r'\s+', ' ', s.strip())
                    # Видаляємо пробіли перед крапками/комами
                    s = re.sub(r'\s+([.,;:])', r'\1', s)
                    # Уніфікуємо тире
                    s = s.replace(' - ', ' – ').replace('—', '–')
                    return s
                
                # Витягуємо локальні джерела
                local_sources = []
                match = source_block_re.search(content)
                if match:
                    raw_sources = match.group(1).strip().split('\n')
                    content = source_block_re.sub('', content).strip()
                    
                    for s in raw_sources:
                        clean_s = re.sub(r'^\d+\.\s*', '', s.strip())
                        if clean_s:
                            # Нормалізуємо джерело
                            normalized = normalize_source(clean_s)
                            local_sources.append(normalized)
                            all_sources_set.add(normalized)

                # Видаляємо дублюючий заголовок на початку контенту (AI часто дублює)
                # Шукаємо рядки типу "Розділ 1. Назва" або "1.1 Назва" на початку
                lines = content.split('\n')
                if lines:
                    first_line = lines[0].strip().lower()
                    # Якщо перший рядок схожий на заголовок - видаляємо
                    if (first_line.startswith('розділ') or 
                        re.match(r'^\d+\.\d*\s', first_line) or
                        title.lower() in first_line):
                        lines = lines[1:]  # Пропускаємо перший рядок
                        # Видаляємо порожні рядки на початку
                        while lines and not lines[0].strip():
                            lines = lines[1:]
                    content = '\n'.join(lines)

                # Форматування
                content = re.sub(r'\n{3,}', '\n\n', content)
                content = content.replace('\n\n', '\n')

                section_entry['content'] = content
                section_entry['local_sources'] = local_sources

            except IOError as e:
                section_entry['content'] = f"[Помилка читання файлу: {e}]"
        else:
            section_entry['content'] = "[Файл ще не згенеровано або не знайдено]"

        sections_data.append(section_entry)

    # ===== PASS 2: Сортуємо джерела за алфавітом =====
    sorted_sources = sorted(all_sources_set, key=lambda x: x.lower())
    # Створюємо мапу: текст_джерела -> фінальний номер (1-based)
    source_to_final_id = {src: idx + 1 for idx, src in enumerate(sorted_sources)}

    # ===== PASS 3: Заміна цитат та запис файлу =====
    try:
        with open(final_filepath, 'w', encoding='utf-8') as final_file:
            final_file.write(f"КУРСОВА РОБОТА\n")
            final_file.write(f"Тема: {topic}\n")
            final_file.write("=" * 80 + "\n\n")

            for section in sections_data:
                final_file.write(f"{section['header']}\n\n")

                content = section['content']
                local_sources = section['local_sources']

                if local_sources:
                    # Створюємо мапу: локальний номер -> фінальний номер
                    local_to_final = {}
                    for i, src_text in enumerate(local_sources):
                        local_idx = str(i + 1)
                        final_idx = source_to_final_id.get(src_text, i + 1)
                        local_to_final[local_idx] = str(final_idx)

                    # Заміна цитат
                    def replace_citation(m):
                        old_num = m.group(1)
                        return f"[{local_to_final.get(old_num, old_num)}]"
                    
                    content = citation_re.sub(replace_citation, content)

                final_file.write(content)
                final_file.write("\n\n")

            # Список джерел (вже відсортований за алфавітом)
            if sorted_sources:
                final_file.write("СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ\n\n")
                for i, src in enumerate(sorted_sources, 1):
                    final_file.write(f"{i}. {src}\n")

        # Окремий файл з джерелами
        if sorted_sources:
            with open(sources_filepath, 'w', encoding='utf-8') as f:
                f.write("СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ\n\n")
                for i, src in enumerate(sorted_sources, 1):
                    f.write(f"{i}. {src}\n")
            logger.info(f"Список джерел (за алфавітом) збережено: {sources_filepath}")

        logger.info(f"Усі частини успішно об'єднано у файл: {final_filepath}")
        return final_filepath

    except Exception as e:
        logger.error(f"Помилка запису у фінальний файл: {e}")
        return None

class CourseworkGenerator:
    def __init__(self, config: dict, log_callback: Optional[Callable[[str], None]] = None):
        self.config = config
        self.log_callback = log_callback
        self.ai_provider = get_ai_provider(self.config)
        self.orchestrator = Orchestrator(self.ai_provider, self.config)

    def log(self, message: str):
        logger.info(message)
        if self.log_callback:
            self.log_callback(message)

    def run(self, topic: str, toc_text: str = None, input_toc_file: str = None, output_filename: str = '_final_course_paper.txt', overrides: Dict[str, str] = None) -> str:
        """
        Запускає процес генерації.
        :param topic: Тема курсової.
        :param toc_text: Текст змісту.
        :param overrides: Словник ручних налаштувань методів.
        """
        try:
            self.config['project_settings']['topic'] = topic
            output_dir = self.config['project_settings'].get('output_dir', 'output/')
            output_dir = f"{output_dir}{sanitize_filename(topic)}"
            
            if not os.path.exists(output_dir):
                 os.makedirs(output_dir)
                 self.log(f"Створено папку для результатів: {output_dir}")

            # 3. Розбір змісту
            if toc_text:
                # Використовуємо parse_lines напряму
                lines = toc_text.splitlines()
                toc_structure = parse_lines(lines)
            elif input_toc_file:
                toc_structure = parse_toc(input_toc_file)
            else:
                raise ValueError("Не вказано ні toc_text, ні input_toc_file")

            # 4. ПЛАНУВАННЯ
            self.log("--- ФАЗА 1: ПЛАНУВАННЯ ---")
            generation_plan = self.orchestrator.create_plan(toc_structure, overrides=overrides)
            
            # 5. ВИКОНАННЯ
            self.log("--- ФАЗА 2: ВИКОНАННЯ ---")
            self.orchestrator.execute_plan(generation_plan, output_dir)
            
            # 6. Об'єднання
            final_path = combine_output_files(output_dir, output_filename, generation_plan, topic)

            self.log("Роботу успішно завершено!")
            return final_path

        except Exception as e:
            self.log(f"Критична помилка виконання: {e}")
            logger.error(f"Критична помилка виконання: {e}", exc_info=True)
            raise e

def main():
    parser = argparse.ArgumentParser(description="Генератор курсових робіт 2.0 (Агентна система)")
    parser.add_argument('--config', default='config.yaml', help='Шлях до файлу конфігурації.')
    parser.add_argument('--topic', help='Тема курсової роботи.')
    parser.add_argument('--output-file', default='_final_course_paper.txt', help='Назва фінального файлу.')
    parser.add_argument('--dry-run', action='store_true', help='Запуск без реальних викликів AI (тестовий режим).')

    args = parser.parse_args()

    try:
        config = load_config(args.config)
        
        # Визначаємо тему
        if args.topic:
            topic = args.topic
        else:
            topic = config['project_settings'].get('topic', 'Не вказана тема')

        # Add dry-run setting to config
        if args.dry_run:
            if 'project_settings' not in config:
                config['project_settings'] = {}
            config['project_settings']['dry_run'] = True
            print("!!! DRY RUN MODE ACTIVATED !!!")

        input_toc_file = config['project_settings'].get('input_toc_file', 'input/toc.txt')

        generator = CourseworkGenerator(config)
        generator.run(topic=topic, input_toc_file=input_toc_file, output_filename=args.output_file)

    except Exception as e:
        logger.error(f"Аварійне завершення: {e}")

if __name__ == "__main__":
    main()
