from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseScraper(ABC):
    @property
    @abstractmethod
    def target_domain(self) -> str:
        """Returns domain this scraper handles (e.g., nike.com)"""
        pass
    @abstractmethod
    async def scrape_products(self, query: str) -> List[Dict[str, Any]]:
        """Executes the asynchronous scraping logic and returns standardized dictionaries"""
        pass
