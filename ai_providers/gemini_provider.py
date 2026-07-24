# ai_providers/gemini_provider.py
"""Google Gemini provider — async через google-generativeai SDK."""
import json
import logging
from typing import Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .base_provider import BaseAIProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """Реалізація для Gemini API (Gemini 2.0 Flash / Pro)."""

    def __init__(self, api_key: str, model: str, config_params: dict):
        super().__init__(api_key, model, config_params)
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError(
                "Встановіть SDK: pip install google-generativeai"
            ) from e
        genai.configure(api_key=self.api_key)
        self._genai = genai
        gen = config_params.get("generation_params", {}) or {}
        self.default_temp: float = gen.get("temperature", 0.7)
        self.default_max_tokens: int = gen.get("max_tokens", 8000)

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
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
        gen_config = self._genai.types.GenerationConfig(
            temperature=temperature if temperature is not None else self.default_temp,
            max_output_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
            response_mime_type="application/json" if response_format else "text/plain",
        )
        full_prompt = (system + "\n\n" + prompt) if system else prompt

        model = self._genai.GenerativeModel(self.model)
        # google-generativeai має sync API, але обгортка асинхронна — викликаємо у threadpool
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(full_prompt, generation_config=gen_config),
        )

        # Безпечне витягання тексту: response.text кидає виняток, якщо finish_reason != STOP.
        try:
            cand = response.candidates[0] if response.candidates else None
            finish = getattr(cand, "finish_reason", None)
            finish_name = getattr(finish, "name", str(finish))
            if finish_name == "MAX_TOKENS":
                logger.warning(
                    f"Gemini обрізав відповідь по max_tokens="
                    f"{gen_config.max_output_tokens}"
                )
            # Збираємо текст з частин навіть при обриві
            parts = []
            if cand and cand.content and cand.content.parts:
                for p in cand.content.parts:
                    if getattr(p, "text", None):
                        parts.append(p.text)
            text = "".join(parts) if parts else (response.text or "")
        except Exception as e:
            logger.error(f"Gemini: не вдалося витягти текст: {e}")
            text = ""
        return text.strip()
