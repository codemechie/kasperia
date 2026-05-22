import inspect
import types
import logging
import traceback
from state import state

logger = logging.getLogger("ScraperEvaluator")

def load_agent_scraper(domain: str, python_code_str: str) -> dict:
    """Dynamically compiles a string of Python code into an isolated module,
        extracts the scraper instance, and binds it to the live state registry.

        Returns {"success": True} on success,
                {"success": False, "error": "..."} on failure.
    """
    # 1. Establish an isolated module name space
    module_name = f"dynamic_scraper_{domain.replace('.', '_')}"
    dynamic_module = types.ModuleType(module_name)

    # 2. Grant basic built-in language execution capability
    dynamic_module.__dict__.update({
        "__builtins__": __builtins__,
    })

    try:
        # 3. Compile and execute inside the local module scope
        compiled_code = compile(python_code_str, filename=f"<agent_{domain}", mode="exec")
        exec(compiled_code, dynamic_module.__dict__)

        # 4. Enforce convention: The LLM must define a class named 'Scraper'
        if "Scraper" not in dynamic_module.__dict__:
            logger.error(f"Validation failed: Class 'Scraper' not found in agent output for {domain}")
            return {"success": False, "error": "Class 'Scraper' not found in agent output"}
        scraper_class = dynamic_module.__dict__["Scraper"]

        # 6. Instantiate and live-bind right to your global state container
        scraper = scraper_class()
        scrape_products = getattr(scraper, "scraper_products", None)
        if not inspect.iscoroutinefunction(scrape_products):
            return {
                "success": False,
                "error": "Scraper.scrape_products must be defined as an async method."
            }
        state.scraper_registry[domain] = scraper
        logger.info(f"Live-registered dynamic parser into state.scraper_registry: {domain}")
        return {"success": True}

    except Exception as e:
        error = traceback.format_exc()
        logger.error("Validation failed:\n%s", error)
        return {"success": False, "error": error}

