# ai_providers/base_provider.py
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class BaseAIProvider(ABC):
    """Абстрактний базовий клас для всіх AI провайдерів."""

    def __init__(self, api_key: str, model: str, config_params: dict):
        self.api_key = api_key
        self.model = model
        self.config_params = config_params # Зберігаємо інші параметри з конфігу

    @abstractmethod
    def generate_text(self,
                      current_prompt: str,
                      history: Optional[List[Dict[str, str]]] = None, # <<< Додаємо історію
                      **kwargs) -> str:
        """
        Генерує текст на основі поточного запиту та попередньої історії.

        Args:
            current_prompt: Новий запит від користувача для цього кроку.
            history: Список попередніх повідомлень [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}].
            kwargs: Додаткові параметри генерації.

        Returns:
            Згенерований текст відповіді від асистента.
        """
        pass

    def _load_credentials(self):
        """Метод для завантаження/перевірки облікових даних (може бути складнішим)."""
        if not self.api_key:
            raise ValueError(f"API ключ для {self.__class__.__name__} не знайдено або не задано.")
        # Тут можна додати логіку для завантаження з env змінних, якщо ключ не в config.yaml