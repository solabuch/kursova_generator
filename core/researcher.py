# core/researcher.py
import logging
from duckduckgo_search import DDGS
from typing import List, Dict

logger = logging.getLogger(__name__)

class Researcher:
    """
    Клас для пошуку інформації в Інтернеті за допомогою DuckDuckGo.
    Універсальний пошук для будь-якої тематики.
    """
    def __init__(self, region: str = "wt-wt", max_results: int = 5):
        self.region = region
        self.max_results = max_results
        self.ddgs = DDGS()

    def search(self, query: str) -> str:
        """
        Виконує пошук за запитом і повертає зведений текстовий результат.
        """
        logger.info(f"Виконання пошукового запиту: {query}")
        try:
            results = self.ddgs.text(query, region=self.region, max_results=self.max_results)
            if not results:
                return "Пошук не дав результатів."
            
            summary = f"Результати пошуку для '{query}':\n\n"
            for res in results:
                title = res.get('title', 'No Title')
                body = res.get('body', '')
                href = res.get('href', '')
                summary += f"- **{title}**: {body}\n  Link: {href}\n\n"
            
            return summary
            
        except Exception as e:
            logger.error(f"Помилка під час пошуку: {e}")
            return f"Сталася помилка під час пошуку: {str(e)}"

    def search_entity(self, entity: str, context: str = "") -> str:
        """
        Універсальний метод для пошуку інформації про сутність (компанія, регіон, поняття тощо).
        :param entity: Назва сутності для пошуку
        :param context: Додатковий контекст (наприклад, тема роботи)
        """
        # Формуємо універсальний запит без специфічних ключових слів
        if context:
            query = f"{entity} {context}"
        else:
            query = f"{entity} інформація дані статистика"
        return self.search(query)

    def get_company_info(self, company_name: str, location: str = "") -> str:
        """
        Спеціалізований метод для пошуку інформації про компанію.
        Залишений для зворотної сумісності.
        """
        return self.search_entity(company_name, location)

    def get_regional_stats(self, topic: str, region: str) -> str:
        """
        Пошук статистики по темі та регіону.
        """
        query = f"статистика {topic} {region} 2023 2024 дані показники"
        return self.search(query)

    def get_topic_info(self, topic: str) -> str:
        """
        Загальний пошук інформації по темі (для теоретичних розділів).
        """
        query = f"{topic} теорія визначення поняття наукові джерела"
        return self.search(query)

