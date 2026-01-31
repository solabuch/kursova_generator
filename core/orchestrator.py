# core/orchestrator.py
import logging
import json
from typing import List, Dict, Any
from core.context_manager import ContextManager
from core.researcher import Researcher
from ai_providers.base_provider import BaseAIProvider
from core.file_handler import save_content

logger = logging.getLogger(__name__)

class Orchestrator:
    """
    Керує процесом планування та генерації курсової роботи.
    - Аналізує зміст (Planner).
    - Визначає тип розділу (Theory vs Practice).
    - Запускає дослідження (Researcher).
    - Генерує контент з відповідним агентом.
    """
    def __init__(self, ai_provider: BaseAIProvider, config: Dict[str, Any]):
        self.ai = ai_provider
        self.config = config
        self.context_manager = ContextManager(model_name=config['providers'][config['active_provider']]['model'])
        self.researcher = Researcher()
        
        # Завантаження промптів
        self.prompts = {
            'planner': self._load_prompt('prompts/planner_prompt.txt'),
            'theory': self._load_prompt('prompts/theory_agent.txt'),
            'practice': self._load_prompt('prompts/practical_agent.txt')
        }

    def _load_prompt(self, path: str) -> str:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"Промпт {path} не знайдено, використовується стандартний.")
            return ""

    def create_plan(self, toc: List[Dict], overrides: Dict[str, str] = None) -> List[Dict]:
        """
        Аналізує зміст і створює план генерації для кожного розділу.
        :param overrides: Словник {full_title: method_type} для примусового вибору методу.
        """
        logger.info("Створення плану генерації...")
        if overrides is None:
            overrides = {}
        
        # Check for dry run
        if self.config.get('project_settings', {}).get('dry_run', False):
            logger.info("Dry Run: Skipping plan generation by AI, returning default plan.")
            for item in toc:
                item['type'] = 'theoretical'
                item['entities'] = []
                item['research_needed'] = False
                item['guidance'] = "Dry Run Guidance"
            return toc

        toc_text = "\n".join([f"{item['number']} {item['title']}" for item in toc])
        
        prompt = self.prompts['planner'].format(toc=toc_text, topic=self.config['project_settings']['topic'])
        
        try:
            response = self.ai.generate_text(prompt, history=[])
            
            # Robust JSON extraction
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = response
            
            # Clean common markdown/formatting artifacts
            json_str = json_str.replace("```json", "").replace("```", "").strip()
            
            # Attempt to fix trailing commas or simple syntax errors if needed (simplified here)
            try:
                plan = json.loads(json_str)
            except json.JSONDecodeError:
                # Fallback: try to repair naive single quotes which is common with weak models
                try:
                    corrected_json = json_str.replace("'", '"')
                    plan = json.loads(corrected_json)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON even after cleanup: {e}")
                    raise ValueError("AI response did not contain valid JSON.")

            # Apply AI plan first
            enrichments = {item.get('number', str(idx)): item for idx, item in enumerate(plan)}
            
            final_plan = []
            for item in toc:
                # Try to match by number, otherwise fallback
                enrichment = enrichments.get(item['number'], {})
                
                # Default from AI or fallback
                item['type'] = enrichment.get('type', 'theoretical')
                item['entities'] = enrichment.get('entities', [])
                item['research_needed'] = enrichment.get('research_needed', False)
                item['guidance'] = enrichment.get('guidance', '')
                
                # Apply Manual Overrides
                # Ми перевіряємо по full_title, бо це унікальний ідентифікатор в межах GUI
                if item['full_title'] in overrides:
                    manual_type = overrides[item['full_title']]
                    if manual_type != 'auto':
                         item['type'] = manual_type
                         logger.info(f"Manual override for '{item['full_title']}': {manual_type}")

                final_plan.append(item)
                
            logger.info("План успішно створено.")
            return final_plan

        except Exception as e:
            logger.error(f"Помилка при створенні плану: {e}. Використовуємо стандартний план (все теорія).")
            # Fallback
            final_plan = []
            for item in toc:
                item['type'] = 'theoretical'
                item['entities'] = []
                item['research_needed'] = False
                
                # Apply Manual Overrides in fallback too
                if item['full_title'] in overrides:
                     manual_type = overrides[item['full_title']]
                     if manual_type != 'auto':
                         item['type'] = manual_type
                
                final_plan.append(item)
            return final_plan


    def execute_plan(self, plan: List[Dict], output_dir: str):
        """
        Виконує генерацію згідно з планом.
        """
        total = len(plan)
        logger.info(f"Початок виконання плану... ({total} розділів)")
        
        for idx, item in enumerate(plan, 1):
            # Прогрес з лічильником
            logger.info(f"[{idx}/{total}] Обробка: {item['full_title']} [{item.get('type', 'theo')}]")
            
            # 1. Дослідження (якщо потрібно або практичний розділ)
            research_summary = ""
            topic = self.config['project_settings']['topic']
            
            # Для практичних розділів завжди шукаємо дані
            if item.get('type') == 'practical' or (item.get('research_needed') and item.get('entities')):
                entities = item.get('entities', [])
                
                if entities:
                    logger.info(f"Пошук інформації для: {entities}")
                    for entity in entities:
                        info = self.researcher.search_entity(entity, context=topic)
                        if "Пошук не дав результатів" not in info:
                            research_summary += f"\nДані про '{entity}':\n{info}\n"
                
                # Якщо немає конкретних даних - шукаємо загальну статистику
                if not research_summary.strip() or "Пошук не дав результатів" in research_summary:
                    logger.info("Збираємо загальну статистику по темі...")
                    stats = self.researcher.get_regional_stats(topic, "Україна")
                    # Подаємо дані як реальні, щоб AI використав їх впевнено
                    research_summary = f"""Актуальні дані для аналізу:
{stats}

Використовуй ці дані в тексті як реальні показники. Формуй таблиці та висновки на їх основі."""

            # 2. Підготовка промпту для агента
            agent_type = item.get('type', 'theoretical')
            prompt_template = self.prompts.get('practice' if agent_type == 'practical' else 'theory')
            
            # Визначаємо, чи це вступ/висновки
            is_intro_or_conc = any(x in item['full_title'].lower() for x in ['вступ', 'висновки', 'резюме'])
            
            if is_intro_or_conc:
                citation_instr = "У цьому розділі ЗАБОРОНЕНО використовувати посилання на джерела. Не додавай жодних [N] цитат."
                source_instr = ""
            else:
                citation_instr = """ПРАВИЛА ПОСИЛАНЬ НА ДЖЕРЕЛА (ОБОВ'ЯЗКОВО ДОТРИМУЙСЯ):
1. Кожен рядок тексту = 1 абзац
2. ПЕРШЕ посилання ставиться НЕ РАНІШЕ 3-го абзацу (тобто абзаци 1 і 2 без посилань)
3. Далі посилання через кожні 2-4 абзаци (випадково обирай інтервал)
4. Номери посилань в тексті НЕ мають йти послідовно (можна [3], потім [1], потім [5])
5. НЕ ставити посилання в кожному абзаці - це виглядає неприродно
6. Використовуй 4-7 різних джерел для розділу"""
                source_instr = """В кінці відповіді надай список використаних джерел у блоці:
[[SOURCE_LIST]]
1. Перше джерело (повний бібліографічний опис)
2. Друге джерело
...
[[/SOURCE_LIST]]

Джерела мають бути реалістичними (українські автори, видавництва, роки 2018-2024)."""

            
            # Контекст з попередніх розділів
            context_history = self.context_manager.get_context()
            
            # Формування повного промпту
            section_prompt = prompt_template.format(
                topic=topic,
                section_title=item['full_title'],
                guidance=item.get('guidance', ''),
                research_data=research_summary,
                methodology=self.config['project_settings']['methodology_summary'],
                citation_instruction=citation_instr,
                source_list_instruction=source_instr
            )
            
            # 3. Генерація
            try:
                if self.config.get('project_settings', {}).get('dry_run', False):
                    content = f"[DRY RUN MODE]\n\nGenerated content for section: {item['full_title']}\n\nKey Entities identified: {item.get('entities')}\n\nResearch Summary:\n{research_summary}"
                    if not is_intro_or_conc:
                        content += "\n\n[[SOURCE_LIST]]\n1. Test Source A\n2. Test Source B\n[[/SOURCE_LIST]]"
                    logger.info(f"[{idx}/{total}] Dry run generation completed")
                else:
                    content = self.ai.generate_text(section_prompt, history=context_history)
                    logger.info(f"[{idx}/{total}] Генерацію завершено")
                
                # 4. Збереження та оновлення контексту
                save_content(output_dir, item, content)
                
                # Додаємо в історію контексту
                self.context_manager.add_message("user", f"Write section: {item['full_title']}")
                self.context_manager.add_message("assistant", content)
                
            except Exception as e:
                logger.error(f"[{idx}/{total}] ПОМИЛКА генерації для {item['full_title']}: {e}")
                # Зберігаємо помилку замість втрати розділу
                error_content = f"[ПОМИЛКА ГЕНЕРАЦІЇ]\n\nРозділ: {item['full_title']}\nПомилка: {str(e)}\n\nБудь ласка, перегенеруйте цей розділ вручну."
                save_content(output_dir, item, error_content)

