from state import state
from .nike import NikeScraper
from .adidas import AdidasScraper

# Auto-register adapted scrapers into the live state registry
for scraper in [NikeScraper(), AdidasScraper()]:
    state.scraper_registry[scraper.target_domain] = scraper

# Boot-scan: load persisted generated scrapers (validated on write, no re-check needed)
import importlib
import pathlib

generated_dir = pathlib.Path(__file__).parent / "generated"
for py_file in sorted(generated_dir.glob("*.py")):
    if py_file.name == "__init__.py":
        continue
    mod = importlib.import_module(f".generated.{py_file.stem}", __package__)
    scraper = mod.Scraper()
    state.scraper_registry[scraper.target_domain] = scraper

def get_scraper(domain: str):
    return state.scraper_registry.get(domain)


def all_scrapers():
    return state.scraper_registry.items()
