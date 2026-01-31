# core/context_manager.py
import logging
import tiktoken
from typing import List, Dict

logger = logging.getLogger(__name__)

class ContextManager:
    """
    Клас для управління контекстом розмови, підрахунку токенів
    та збереження історії в межах лімітів моделі.
    """
    def __init__(self, model_name: str = "gpt-4o", max_tokens: int = 120000):
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.history: List[Dict[str, str]] = []
        self.summary: str = ""  # Сумаризація старих розділів
        try:
            self.encoding = tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.warning(f"Модель {model_name} не знайдена в tiktoken. Використовуємо cl100k_base.")
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Повертає кількість токенів у тексті."""
        return len(self.encoding.encode(text))

    def get_history_tokens(self) -> int:
        """Повертає загальну кількість токенів у поточній історії."""
        total = self.count_tokens(self.summary) if self.summary else 0
        for msg in self.history:
            total += self.count_tokens(msg.get('content', ''))
        return total

    def add_message(self, role: str, content: str):
        """Додає повідомлення до історії."""
        self.history.append({"role": role, "content": content})

    def _summarize_messages(self, messages: List[Dict]) -> str:
        """
        Створює коротку сумаризацію повідомлень.
        Витягує заголовки розділів та перші речення.
        """
        summaries = []
        for msg in messages:
            if msg['role'] == 'user' and 'Write section:' in msg['content']:
                # Витягуємо назву розділу
                section_name = msg['content'].replace('Write section:', '').strip()
                summaries.append(f"- {section_name}")
            elif msg['role'] == 'assistant':
                # Беремо перші 100 символів контенту
                content = msg['content'][:150].replace('\n', ' ').strip()
                if content and summaries:
                    summaries[-1] += f": {content}..."
        
        if summaries:
            return "Попередньо написані розділи:\n" + "\n".join(summaries[:10])  # Максимум 10 розділів
        return ""

    def get_context(self, system_prompt: str = "") -> List[Dict[str, str]]:
        """
        Повертає оптимізовану історію для відправки в API.
        Якщо ліміт перевищено, створює сумаризацію старих розділів.
        """
        current_tokens = self.get_history_tokens()
        system_tokens = self.count_tokens(system_prompt)
        
        available_tokens = self.max_tokens - system_tokens - 4000  # Запас на відповідь
        
        if current_tokens <= available_tokens:
            # Якщо є сумаризація - додаємо її на початок
            if self.summary:
                return [{"role": "system", "content": self.summary}] + self.history
            return self.history
        
        # Контекст перевищує ліміт - потрібна сумаризація
        logger.info(f"Контекст перевищує ліміт ({current_tokens} > {available_tokens}). Сумаризація...")
        
        # Розділяємо на старі та нові повідомлення
        messages_to_keep = []
        messages_to_summarize = []
        current_batch_tokens = 0
        
        # Обираємо скільки останніх повідомлень зберегти (мінімум 4 - 2 пари user/assistant)
        keep_count = min(8, len(self.history))
        
        # Йдемо з кінця, зберігаємо останні
        for i, msg in enumerate(reversed(self.history)):
            if i < keep_count:
                msg_tokens = self.count_tokens(msg['content'])
                if current_batch_tokens + msg_tokens < available_tokens * 0.7:
                    messages_to_keep.insert(0, msg)
                    current_batch_tokens += msg_tokens
                else:
                    break
            else:
                messages_to_summarize.insert(0, msg)
        
        # Сумаризуємо старі повідомлення
        if messages_to_summarize:
            new_summary = self._summarize_messages(messages_to_summarize)
            if self.summary:
                self.summary = self.summary + "\n" + new_summary
            else:
                self.summary = new_summary
            
            # Обмежуємо розмір сумаризації
            if self.count_tokens(self.summary) > 2000:
                # Залишаємо тільки останні рядки
                lines = self.summary.split('\n')
                self.summary = '\n'.join(lines[-15:])
        
        # Оновлюємо історію
        self.history = messages_to_keep
        
        logger.info(f"Оновлено контекст: {len(messages_to_keep)} повідомлень + сумаризація")
        
        result = []
        if self.summary:
            result.append({"role": "system", "content": self.summary})
        result.extend(messages_to_keep)
        
        return result

    def clear_history(self):
        self.history = []
        self.summary = ""

