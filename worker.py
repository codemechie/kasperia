import asyncio
import logging
import os
import httpx
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
import re
from urllib.parse import quote

from state import state
from scrapers.evaluator import load_agent_scraper

#a strict allowlist or hostname regex to reject
#values containing schemes, paths, ports or dangerous characters to prevent SSRF:
_DOMAIN_RE = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)

# Search URL patterns to try in order (covers most e-commerce platforms)
_SEARCH_PATTERNS = [
    "/search?q={query}",
    "/catalogsearch/result/?q={query}",
    "/s?q={query}",
    "/search?keyword={query}",
    "/p/pl?d={query}",
    "/pl?d={query}",
    "/?s={query}",
]


# Basic background engine logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackgroundWorker")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-r1:8b")

llm_client = AsyncOpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
)

def _clean_dom(html: bytes) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    body = soup.body or soup
    return str(body)[:2000]

async def fetch_target_dom_sample(domain: str, query: str) -> str:
    """Fetches a lightweight snippet of the store's result grid to show to the LLM.
    Tries multiple search URL patterns, then falls back to the homepage.
    """
    if not _DOMAIN_RE.match(domain or ""):
        logger.error(f"Rejecting unsafe domain: {domain!r}")
        return ""

    encoded_query = quote(query or "", safe="")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        # Phase 1: try search URL patterns
        for pattern in _SEARCH_PATTERNS:
            url = f"https://{domain}{pattern.replace('{query}', encoded_query)}"
            try:
                response = await client.get(url, headers=_HEADERS)
                if response.is_success:
                    cleaned = _clean_dom(response.content)
                    if len(cleaned) >= 200:
                        return cleaned
            except Exception:
                continue

        # Phase 2: fallback to homepage for structural context
        try:
            response = await client.get(f"https://{domain}/", headers=_HEADERS)
            if response.is_success:
                cleaned = _clean_dom(response.content)
                if len(cleaned) >= 200:
                    logger.info(f"Falling back to homepage for {domain}")
                    return cleaned
        except Exception:
            pass

    logger.warning(f"Could not fetch any usable DOM content for {domain}")
    return ""

async def start_background_worker():
    """Listens continuously for missing scrapers and queues agent builds."""
    logger.info("Background Scraper-Agent agent fully synchronized...")
    while True:
        job = None
        try:
            job = await state.queue.get()
            domain = job.get("domain")
            query = job.get("query")

            logger.info(f"[Queue] Processing creation demand for domain: {domain}")

            # 1. Fetch Structural Blueprint Context
            html_sample = await fetch_target_dom_sample(domain, query)

            # 1b. Guard: skip codegen if DOM sample is too short to be useful
            if len(html_sample.strip()) < 200:
                logger.warning(f"DOM sample too short ({len(html_sample.strip())} chars) for {domain}. Skipping codegen.")
                continue

            # 2. Invoke Code-Gen Model via agent pipeline
            generated_python_code = await run_llm_codegen_agent(domain, html_sample)

            # --- START SELF-HEALING STATE MACHINE ---
            max_attempts = 3
            current_attempt = 1
            # Configure clean path locations
            safe_name = domain.replace(".", "_")
            file_path = f"scrapers/generated/{safe_name}.py"
            debug_dump_dest = f"scrapers/debug_dump/faulty_{safe_name}.py"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(debug_dump_dest), exist_ok=True)

            while current_attempt <= max_attempts:
                logger.info(f"Running RAM Firewall Evaluation [{current_attempt}/{max_attempts}] for {domain}")

                # Check the code string using in-memory exec() evaluator
                eval_result = load_agent_scraper(domain, generated_python_code.strip())

                is_valid = eval_result.get("success", False)
                if is_valid:
                    # -- ROUTE A: CODE IS VALID ---
                    # 1. Save directly to immaculate cold storage file path
                    try:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(generated_python_code)
                        logger.info(f"Persisted scraper to {file_path}")

                        # Also clean up old debug files if a previous attempt left one behind
                        if os.path.exists(debug_dump_dest):
                            os.remove(debug_dump_dest)

                        logger.info(f"System upgraded! Real-time scraper active for: {domain}")
                        break
                    except OSError as e:
                        logger.error(f"Failed to write {file_path}: {e}")
                        current_attempt += 1
                        continue

                else:
                    # --- ROUTE B: Evaluator detects fault ---
                    logger.warning(f"Real-time build loop failed validation for {domain}")
                    # Dump the faulty code to your hidden staging area so you can debug it later
                    try:
                        os.makedirs(os.path.dirname(debug_dump_dest), exist_ok=True)
                        with open(debug_dump_dest, "w", encoding="utf-8") as f:
                            f.write(generated_python_code.strip())
                        logger.info(f"Faulty module dumped safely to Staging Area: {debug_dump_dest}")
                    except OSError:
                        logger.warning(f"Failed to dump faulty code to {debug_dump_dest}")

                    if current_attempt == max_attempts:
                        logger.error(f"All self-correction limits exhausted for {domain}. Abandoned build.")
                        break

                    # Extract error string context out of dynamic loader function
                    error_msg = "Class 'Scraper' missing or syntax error detected during RAM execution"
                    if isinstance(eval_result, dict) and "error" in eval_result:
                        error_msg = eval_result["error"]
                    logger.info(f"Requesting patch from Debugging Agent for {domain}...")

                    # Hand off the broken code and error trace back to Agent 2
                    # It returns a fresh string, and the loop starts over to test it safely
                    generated_python_code = await run_llm_debugging_agent(domain, generated_python_code, error_msg)

                    current_attempt += 1

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker Loop Exception: {str(e)}")
        finally:
            if job is not None:
                state.queue.task_done()


async def run_llm_codegen_agent(domain: str, html_sample: str) -> str:
    """Calls Ollama to generate a site-specific scraper class from the DOM sample."""
    logger.info(f"[CodeGen] Requesting scraper for {domain}")

    system_prompt = (
        "You are a senior Python scraping engineer. "
        "Write only valid Python code. No markdown, no explanations."
    )

    user_prompt = f"""Write a scraper class for {domain}.

HTML structure of the search results page:
{html_sample}

Requirements:
- class named `Scraper` with async def scrape_products(self, query: str) -> list[dict]
- Each dict must have keys: title, price, currency, product_url, store_name
- Use httpx.AsyncClient for HTTP and BeautifulSoup for parsing
- Import all necessary modules inside the method

Return ONLY raw Python code, no markdown fences, no explanation."""

    response = await llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    code = response.choices[0].message.content or ""
    # Strip markdown code fences if the model wraps output anyway
    if code.startswith("```"):
        first = code.index("\n") + 1
        last = code.rindex("```")
        code = code[first:last]
    code = code.strip()

    logger.info(f"[CodeGen] Received {len(code)} chars from LLM for {domain}")
    return code

async def run_llm_debugging_agent(domain: str, broken_code: str, error_traceback: str) -> str:
    """Calls the LLM to analyze a runtime compilation failure and patch the code."""
    logger.warning(f"[DebuggingAgent] Repairing broken scraper for {domain}")

    system_prompt = (
        "You are a senior automated QA and debugging agent. Your job is to fix "
        "Python code that has failed runtime execution. Return ONLY raw fixed code, no explanation."
    )
    user_prompt = f"""The python scraper code generated for {domain} has failed runtime execution.
    BROKEN CODE RECOVERY:
    {broken_code}
    
    CRITICAL PYTHON TRACEBACK ERROR:
    {error_traceback}
    
    REQUIREMENTS:
    - Fix the explicit syntax error, missing import, or broken attribute found in the traceback.
    - Do NOT rewrite the logic from scratch; isolate and patch the exact line failing.
    - Maintain the structural contract; Class must be named 'Scraper', 
    exposing 'async def scrape_products(self, query: str) -> list[dict]'.
    
    Return ONLY raw fixed code, no markdown fences, no explanation."""
    response = await llm_client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    code = response.choices[0].message.content or ""
    if code.startswith("```"):
        first = code.index("\n") + 1
        last = code.rindex("```")
        code = code[first:last]
    return code.strip()