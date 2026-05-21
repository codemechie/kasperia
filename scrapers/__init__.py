from state import state
from .nike import NikeScraper
from .adidas import AdidasScraper

# Auto-register adapted scrapers into the live state registry
for scraper in [NikeScraper(), AdidasScraper()]:
    state.scraper_registry[scraper.target_domain] = scraper


def get_scraper(domain: str):
    return state.scraper_registry.get(domain)


def all_scrapers():
    return state.scraper_registry.items()
