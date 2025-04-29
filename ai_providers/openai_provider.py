# ai_providers/openai_provider.py
import os
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError # Потрібно встановити: pip install openai
from typing import List, Dict, Optional
from .base_provider import BaseAIProvider
import logging

logger = logging.getLogger(__name__)
load_dotenv()

class OpenaiProvider(BaseAIProvider):
    """Реалізація для OpenAI API."""

    def __init__(self, api_key: str, model: str, config_params: dict):
        # Можна завантажувати ключ з env, якщо він не заданий прямо
        resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY")
        super().__init__(resolved_api_key, model, config_params)
        self._load_credentials()
        try:
            self.client = OpenAI(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Помилка ініціалізації клієнта OpenAI: {e}")
            raise ConnectionError(f"Не вдалося ініціалізувати клієнта OpenAI: {e}")

    def generate_text(self,
                    current_prompt: str,
                    history: Optional[List[Dict[str, str]]] = None,
                    **kwargs) -> str:
        """Генерує текст за допомогою OpenAI API, враховуючи історію."""

        messages = history if history else [] # Копіюємо або створюємо новий список
        messages.append({"role": "user", "content": current_prompt}) # Додаємо поточний запит

        # Логуємо довжину історії (кількість повідомлень та приблизну кількість токенів - опціонально)
        # Повноцінний підрахунок токенів потребує бібліотеки tiktoken
        logger.info(f"Надсилання запиту до OpenAI model: {self.model} з {len(messages)} повідомленнями в історії.")
        # Тут можна додати перевірку на перевищення ліміту токенів, якщо є бібліотека tiktoken

        generation_settings = self.config_params.get('generation_params', {})
        generation_settings.update(kwargs)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages, # <<< Передаємо всю історію
                temperature=generation_settings.get('temperature', 0.7),
                max_tokens=generation_settings.get('max_tokens', 4096), # Переконайтесь, що це значення достатньо велике
                # Додайте інші параметри з generation_settings за потреби
            )
            generated_text = response.choices[0].message.content.strip()
            # Логуємо довжину відповіді
            logger.info(f"Отримано відповідь від OpenAI довжиною ~{len(generated_text)} символів.")
            # УВАГА: Потрібно перевіряти 'finish_reason'. Якщо 'length', відповідь обрізана!
            finish_reason = response.choices[0].finish_reason
            if finish_reason == 'length':
                    logger.warning(f"Відповідь від OpenAI була обрізана через ліміт max_tokens ({generation_settings.get('max_tokens')})!")
            elif finish_reason != 'stop':
                    logger.warning(f"Неочікувана причина завершення генерації: {finish_reason}")

            return generated_text
        except OpenAIError as e:
            logger.error(f"Помилка API OpenAI: {e}")
            return f"Помилка OpenAI API: {e}"
        except Exception as e:
            logger.error(f"Неочікувана помилка під час генерації тексту OpenAI: {e}")
            return f"Неочікувана помилка: {e}"
