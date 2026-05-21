import asyncio
import logging
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


# Basic background engine logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BackgroundWorker")

llm_client = AsyncOpenAI(
    base_url="http://127.0.0.1:11435/v1",
    api_key="ollama",
)

async def fetch_target_dom_sample(domain: str, query:str) -> str:
    """Fetches a lightweight snippet of the store's result grid to show to the LLM"""
    if not _DOMAIN_RE.match(domain or ""):
        logger.error(f"Rejecting unsafe domain: {domain!r}")
        return "<!-- invalid domain -->"
    url = f"https://{domain}/search?q={quote(query or '', safe='')}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            if response.is_success:
                # Truncate the DOM to just structural markers so we don't blow past LLM token limit
                soup = BeautifulSoup(response.content, "html.parser")
                for tag in soup(["script", "style", "noscript", "svg"]):
                    tag.decompose()
                body = soup.body or soup
                return str(body)[:5000]
            logger.warning(f"DOM fetch for {domain} returned HTTP {response.status_code}")
    except Exception as e:
        logger.error(f"Could not retrieve sample DOM markup for {domain}: {str(e)}")
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

            # 2. Invoke Code-Gen Model via agent pipeline
            generated_python_code = await run_llm_codegen_agent(domain, query, html_sample)

            # 3. Dynamic Compilation & Live State Deployment
            success = load_agent_scraper(domain, generated_python_code)
            if success:
                logger.info(f"System upgraded! Real-time scraper active for: {domain}")
            else:
                logger.warning(f"Real-time build loop failed validation for {domain}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Worker Loop Exception: {str(e)}")
        finally:
            if job is not None:
                state.queue.task_done()
async def run_llm_codegen_agent(domain: str, query: str, html_sample: str) -> str:
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
        model="qwen2.5:7b",
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