# ai_providers/openai_provider.py
import logging
from typing import Optional

from openai import APIError, AsyncOpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .base_provider import BaseAIProvider

logger = logging.getLogger(__name__)


class OpenaiProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str, config_params: dict):
        super().__init__(api_key, model, config_params)
        self.client = AsyncOpenAI(api_key=self.api_key)
        gen = config_params.get("generation_params", {}) or {}
        self.default_temp: float = gen.get("temperature", 0.7)
        self.default_max_tokens: int = gen.get("max_tokens", 8000)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type((APIError, RateLimitError)),
        reraise=True,
    )
    async def generate(
        self,
        prompt: str,
        *,
        system: Optional[str] = None,
        response_format: Optional[dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.default_temp,
            "max_tokens": max_tokens if max_tokens is not None else self.default_max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        logger.debug(f"OpenAI → {self.model}, prompt={len(prompt)} chars")
        response = await self.client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        if choice.finish_reason == "length":
            logger.warning(
                f"OpenAI обрізав відповідь по max_tokens={kwargs['max_tokens']}"
            )

        return (choice.message.content or "").strip()
