# main.py
import yaml
import importlib
import logging
import os
import argparse
from typing import List, Dict

# Імпортуємо потрібні модулі з нашого проєкту
from core.toc_parser import parse_toc
from core.file_handler import save_content, sanitize_filename
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

def load_prompt_template(filepath: str) -> str:
    """Завантажує шаблон промпту з файлу."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Файл шаблону промпту не знайдено: {filepath}")
        raise
    except Exception as e:
        logger.error(f"Помилка читання файлу шаблону промпту {filepath}: {e}")
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
    config_params = provider_config # Передаємо всі параметри провайдера

    if not api_key:
         # Спробувати завантажити з змінної середовища, якщо не задано явно
         api_key_env_var = f"{provider_name.upper()}_API_KEY" # e.g., OPENAI_API_KEY
         api_key = os.environ.get(api_key_env_var)
         logger.info(f"Завантажено API ключ для {provider_name} зі змінної середовища {api_key_env_var}")
         if not api_key:
              logger.warning(f"API ключ для {provider_name} не знайдено ні в config.yaml, ні в змінній середовища {api_key_env_var}.")
              # Можна або викликати помилку, або продовжити (деякі API можуть працювати без ключа з обмеженнями)
              # raise ValueError(f"API ключ для {provider_name} не знайдено.")


    if not model:
        raise ValueError(f"Не вказано 'model' для провайдера '{provider_name}' у конфігурації.")

    try:
        # Динамічно імпортуємо модуль провайдера
        module_path = f"ai_providers.{provider_name}_provider"
        provider_module = importlib.import_module(module_path)

        # Отримуємо клас провайдера (очікуємо назву типу OpenAIProvider, GeminiProvider)
        class_name = f"{provider_name.capitalize()}Provider"
        ProviderClass = getattr(provider_module, class_name)

        # Створюємо екземпляр класу
        instance = ProviderClass(api_key=api_key, model=model, config_params=config_params)
        logger.info(f"Створено екземпляр AI провайдера: {class_name} з моделлю {model}")
        return instance

    except ModuleNotFoundError:
        logger.error(f"Модуль провайдера не знайдено: {module_path}.py")
        raise ImportError(f"Перевірте наявність файлу {module_path}.py")
    except AttributeError:
        logger.error(f"Клас провайдера '{class_name}' не знайдено у модулі {module_path}.py")
        raise ImportError(f"Перевірте назву класу в {module_path}.py")
    except Exception as e:
         logger.error(f"Помилка при створенні AI провайдера {provider_name}: {e}")
         raise

def combine_output_files(output_dir: str, final_filename: str, structure: list[dict], topic: str):
    """
    Об'єднує згенеровані файли в один фінальний файл
    відповідно до порядку в структурі змісту.
    """
    final_filepath = os.path.join(output_dir, final_filename)
    logger.info(f"Початок об'єднання файлів у: {final_filepath}")

    try:
        with open(final_filepath, 'w', encoding='utf-8') as final_file:
            # Додаємо заголовок роботи
            final_file.write(f"КУРСОВА РОБОТА\n")
            final_file.write(f"Тема: {topic}\n")
            final_file.write("=" * 80 + "\n\n") # Роздільник

            # Проходимо по структурі змісту для правильного порядку
            for item in structure:
                # --- Реконструкція імені файлу (має бути ідентичною до логіки в save_content) ---
                number_part = str(item.get('number', 'unknown')).replace('.', '_').replace(' ', '_')
                # Використовуємо ТІЛЬКИ назву для імені файлу, щоб уникнути проблем з довгими 'full_title'
                filename_base = sanitize_filename(item.get('title', 'untitled'))
                individual_filename = f"level{item.get('level', 0)}_{number_part}_{filename_base}.txt"
                individual_filepath = os.path.join(output_dir, individual_filename)
                # --- Кінець реконструкції ---

                logger.debug(f"Додавання файлу: {individual_filepath}")

                # Додаємо заголовок розділу/підрозділу в фінальний файл
                final_file.write(f"--- {item.get('full_title', 'НЕВІДОМИЙ РОЗДІЛ')} ---\n\n")

                if os.path.exists(individual_filepath):
                    try:
                        with open(individual_filepath, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                        # Записуємо вміст файлу
                        final_file.write(content) 
                        # Додаємо роздільник між частинами
                        final_file.write("\n\n" + "=" * 80 + "\n\n")
                    except IOError as e:
                        logger.warning(f"Не вдалося прочитати файл {individual_filepath}: {e}")
                        final_file.write(f"[Помилка: Не вдалося завантажити вміст з файлу {individual_filename}]\n\n")
                        final_file.write("\n\n" + "=" * 80 + "\n\n") # Додаємо роздільник навіть якщо помилка
                else:
                    logger.warning(f"Файл не знайдено для об'єднання: {individual_filepath}")
                    final_file.write(f"[Помилка: Файл {individual_filename} не знайдено]\n\n")
                    final_file.write("\n\n" + "=" * 80 + "\n\n") # Додаємо роздільник

        logger.info(f"Усі частини успішно об'єднано у файл: {final_filepath}")

    except IOError as e:
        logger.error(f"Помилка запису у фінальний файл {final_filepath}: {e}")
    except Exception as e:
        logger.error(f"Неочікувана помилка під час об'єднання файлів: {e}", exc_info=True)

def main():
    parser = argparse.ArgumentParser(description="Генератор курсових робіт за допомогою AI з підтримкою контексту.")
    # ... (аргументи залишаються ті ж самі) ...
    parser.add_argument('--config', default='config.yaml', help='Шлях до файлу конфігурації.')
    parser.add_argument('--topic', help='Тема курсової роботи (перевизначає значення з config).')
    parser.add_argument('--output-file', default='_final_course_paper.txt', help='Назва фінального об\'єднаного файлу.')

    args = parser.parse_args()

    # Ініціалізуємо змінну для історії ПЕРЕД блоком try
    conversation_history: List[Dict[str, str]] = []

    try:
        # 1. Завантаження конфігурації
        config = load_config(args.config)
        project_settings = config.get('project_settings', {})

        # ... (визначення теми, шляхів, перевірка output_dir) ...
        topic = args.topic or project_settings.get('topic', 'Не вказана тема')
        methodology = project_settings.get('methodology_summary', 'Загальні академічні вимоги.')
        input_toc_file = project_settings.get('input_toc_file', 'input/toc.txt')
        output_dir = project_settings.get('output_dir', 'output/')
        output_dir = f"{output_dir}{sanitize_filename(topic)}" # Додаємо назву теми до шляху
        prompt_template_file = project_settings.get('prompt_template_file', 'prompts/section_prompt.txt')
        project_topic_area = "Туризм та готельно-ресторанний бізнес"

        if not os.path.exists(output_dir):
             os.makedirs(output_dir)
             logger.info(f"Створено папку для результатів: {output_dir}")

        # 2. Завантаження шаблону промпту
        prompt_template = load_prompt_template(prompt_template_file)

        # 3. Ініціалізація AI провайдера
        ai_provider = get_ai_provider(config)

        # 4. Розбір файлу змісту
        toc_structure = parse_toc(input_toc_file)

        # <<< Ініціалізація історії розмови >>>
        # Можна додати початкове системне повідомлення, якщо потрібно
        # conversation_history = [
        #     {"role": "system", "content": f"Ти пишеш курсову роботу на тему '{topic}'. Дотримуйся академічного стилю та вимог: {methodology}"}
        # ]
        conversation_history = [] # Починаємо з порожньої історії

        # 5. Генерація контенту для кожного пункту змісту ЗІ ЗБЕРЕЖЕННЯМ ІСТОРІЇ
        logger.info("Початок генерації контенту для курсової (з контекстом)...")
        generation_successful = True
        for item in toc_structure:
            logger.info(f"--- Генерація для: {item['full_title']} (Рівень: {item['level']}) ---")

            # Формуємо поточний промпт для цього пункту
            level_info = f"Рівень {item['level']}"
            # Зверніть увагу: сам шаблон промпту може НЕ потребувати змін,
            # бо контекст буде передаватись через історію.
            # Але можна додати фразу типу "Продовжуючи попереднє обговорення..."
            current_user_prompt = prompt_template.format(
                project_topic_area=project_topic_area,
                project_topic=topic,
                section_title=item['full_title'],
                section_level_info=level_info,
                methodology=methodology
            )
            # Додаємо інструкцію про контекст (опціонально, модель має зрозуміти з історії)
            current_user_prompt += "\n\nВраховуй попередньо написаний текст при генерації цієї частини для забезпечення логічного зв'язку та уникнення повторів."


            # <<< УВАГА: Потенційна проблема ліміту контекстного вікна >>>
            # Перед викликом API варто перевірити загальну довжину історії + нового промпту.
            # Якщо вона наближається до ліміту моделі, потрібно застосувати стратегію:
            # 1. Обрізка старих повідомлень (найпростіше, але втрачається ранній контекст).
            # 2. Сумаризація старих частин (складніше).
            # Поки що реалізуємо без обрізки, покладаючись на велике вікно сучасних моделей,
            # але додамо попередження.
            # Для підрахунку токенів потрібна бібліотека tiktoken для OpenAI
            # try:
            #     import tiktoken
            #     encoding = tiktoken.encoding_for_model(ai_provider.model) # Може викинути помилку, якщо модель невідома tiktoken
            #     num_tokens = len(encoding.encode(str(conversation_history) + current_user_prompt)) # Дуже приблизно! Точніше рахувати для кожного повідомлення.
            #     logger.info(f"Приблизна кількість токенів у поточному запиті: {num_tokens}")
            #     # Порівняти num_tokens з лімітом моделі мінус max_tokens для відповіді
            # except ImportError:
            #     logger.warning("Бібліотека tiktoken не встановлена. Неможливо точно оцінити розмір контексту.")
            # except Exception as e:
            #      logger.warning(f"Не вдалося оцінити розмір контексту за допомогою tiktoken: {e}")

            # <<< Виклик AI провайдера з історією >>>
            try:
                generated_content = ai_provider.generate_text(
                    current_prompt=current_user_prompt,
                    history=conversation_history # Передаємо всю поточну історію
                )

                # <<< Оновлення історії розмови >>>
                conversation_history.append({"role": "assistant", "content": generated_content})

                # Зберігаємо результат поточного кроку
                save_content(output_dir, item, generated_content.replace('\n\n', '\n'))
                logger.info(f"--- Завершено для: {item['full_title']} ---")

            except Exception as e:
                 logger.error(f"Помилка під час генерації або збереження для '{item['full_title']}': {e}", exc_info=True)
                 generation_successful = False
                 # Якщо була помилка, НЕ додаємо цей крок до історії, щоб уникнути поширення помилки? Або додаємо з позначкою?
                 # Поки що просто пропускаємо додавання до історії при помилці.

            # time.sleep(2) # Пауза
        logger.info(f"Історію повідомлень {conversation_history}.")
        
        # 6. Об'єднання файлів
        if generation_successful:
             logger.info("Генерацію всіх частин (з контекстом) завершено.")
             combine_output_files(output_dir, args.output_file, toc_structure, topic)
        else:
             logger.warning("Генерація не була повністю успішною. Спробуємо об'єднати те, що є.")
             combine_output_files(output_dir, args.output_file, toc_structure, topic) # Об'єднуємо те, що вдалося згенерувати

        logger.info("Роботу скрипта завершено!")

    except (FileNotFoundError, ValueError, ImportError, yaml.YAMLError, ConnectionError) as e:
        logger.error(f"Критична помилка: {e}")
    except Exception as e:
        logger.error(f"Непередбачена помилка виконання: {e}", exc_info=True)


if __name__ == "__main__":
    main()