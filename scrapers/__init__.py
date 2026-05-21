from .nike import NikeScraper
from .adidas import AdidasScraper

SCRAPERS = {
    "nike": NikeScraper(),
    "adidas": AdidasScraper(),
}

def get_scraper(brand: str):
    return SCRAPERS.get(brand.lower())

def all_scrapers():
    return SCRAPERS.items()
