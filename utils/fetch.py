import asyncio
import logging

logger = logging.getLogger("FetchUtil")

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    logger.warning("curl_cffi not installed.")

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    logger.warning("cloudscraper not installed.")

import httpx


_IMPERSONATE_TARGETS = [
    "chrome124",
    "chrome123",
    "chrome120",
    "chrome110",
    "safari17_0",
    "safari15_5",
]


async def _try_homepage_cookies(session, domain: str, headers, timeout):
    for host in [f"https://www.{domain}/", f"https://{domain}/"]:
        try:
            resp = await session.get(host, headers=headers, allow_redirects=True, timeout=timeout)
            if resp.ok:
                logger.info(f"Homepage cookie fetch succeeded for {domain} via {host}")
                return resp.cookies if hasattr(resp, "cookies") else None
        except Exception:
            continue
    return None


def _wrap_response(resp):
    class WrappedResponse:
        def __init__(self, content, status_code, headers, url, is_success):
            self.content = content
            self.status_code = status_code
            self.headers = headers
            self.url = url
            self.is_success = is_success

        def raise_for_status(self):
            if not self.is_success:
                raise httpx.HTTPStatusError(
                    f"HTTP {self.status_code}", request=None, response=self
                )

    return WrappedResponse(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers) if hasattr(resp, "headers") else {},
        url=str(resp.url) if hasattr(resp, "url") else "",
        is_success=resp.ok if hasattr(resp, "ok") else (200 <= resp.status_code < 400),
    )


async def fetch_page(
    url: str,
    headers: dict | None = None,
    follow_redirects: bool = True,
    timeout: float = 10.0,
    domain_for_cookies: str | None = None,
) -> httpx.Response | None:
    if HAS_CURL_CFFI:
        for target in _IMPERSONATE_TARGETS:
            try:
                async with AsyncSession(impersonate=target) as session:
                    if domain_for_cookies:
                        await _try_homepage_cookies(session, domain_for_cookies, None, timeout)
                    resp = await session.get(
                        url,
                        headers=None,
                        allow_redirects=follow_redirects,
                        timeout=timeout,
                    )
                    if resp.ok:
                        logger.info(f"curl_cffi({target}) succeeded: {url} -> {resp.status_code}")
                        return _wrap_response(resp)
                    else:
                        logger.warning(f"curl_cffi({target}) got {resp.status_code} for {url} (final URL: {resp.url})")
            except Exception as e:
                logger.warning(f"curl_cffi({target}) failed for {url}: {e}")

    if HAS_CLOUDSCRAPER:
        try:
            scraper = cloudscraper.create_scraper()
            resp = await asyncio.to_thread(
                scraper.get, url, headers=headers or {}, timeout=timeout,
            )
            if resp.ok:
                logger.info(f"cloudscraper succeeded: {url} -> {resp.status_code}")
                return _wrap_response(resp)
            else:
                logger.warning(f"cloudscraper got {resp.status_code} for {url}")
        except Exception as e:
            logger.warning(f"cloudscraper failed for {url}: {e}")

    try:
        async with httpx.AsyncClient(follow_redirects=follow_redirects) as client:
            response = await client.get(url, headers=headers or {}, timeout=timeout)
            if response.is_success:
                return response
            logger.warning(f"httpx got {response.status_code} for {url}")
            return None
    except Exception as e:
        logger.warning(f"httpx failed for {url}: {e}")
        return None
