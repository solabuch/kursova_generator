# ai_providers/base_provider.py
from abc import ABC, abstractmethod
from typing import Optional


class BaseAIProvider(ABC):
    """Асинхронний інтерфейс LLM-провайдера."""

    def __init__(self, api_key: str, model: str, config_params: dict):
        if not api_key:
            raise ValueError(f"API ключ для {self.__class__.__name__} не задано.")
        self.api_key = api_key
        self.model = model
        self.config_params = config_params

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        response_format: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Одноразова генерація без історії. Історія — на рівні orchestrator (якщо потрібно)."""
        ...
