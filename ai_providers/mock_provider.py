# ai_providers/mock_provider.py
from typing import List, Dict, Optional
from .base_provider import BaseAIProvider
import json

class MockProvider(BaseAIProvider):
    """Mock Provider for debugging without API keys."""

    def generate_text(self, current_prompt: str, history: Optional[List[Dict[str, str]]] = None, **kwargs) -> str:
        # Check if this is a Planning request (heuristic based on prompt content)
        if "JSON" in current_prompt and "number" in current_prompt:
            # Return a valid JSON plan
            return json.dumps([
                {
                    "number": "Розділ 1",
                    "type": "theoretical",
                    "entities": [],
                    "research_needed": False,
                    "guidance": "Test guidance"
                }
            ])
        else:
            # Return dummy content
            return "Це тестовий згенерований текст для розділу. " * 10
