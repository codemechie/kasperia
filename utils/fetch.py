import logging

logger = logging.getLogger("FetchUtil")

try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    logger.warning("curl_cffi not installed. Falling back to httpx for HTTP requests.")

import httpx


async def fetch_page(
    url: str,
    headers: dict | None = None,
    follow_redirects: bool = True,
    timeout: float = 10.0,
) -> httpx.Response | None:
    """Fetch a URL using curl_cffi (with browser TLS impersonation) if available,
    falling back to httpx otherwise. Returns an httpx.Response-like object or None."""

    if HAS_CURL_CFFI:
        try:
            async with AsyncSession(impersonate="chrome") as session:
                resp = await session.get(
                    url,
                    headers=headers or {},
                    allow_redirects=follow_redirects,
                    timeout=timeout,
                )
                if resp.ok:
                    # Wrap curl_cffi response in an httpx-like interface
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

                    wrapped = WrappedResponse(
                        content=resp.content,
                        status_code=resp.status_code,
                        headers=dict(resp.headers),
                        url=str(resp.url),
                        is_success=resp.ok,
                    )
                    logger.info(f"curl_cffi succeeded: {url} -> {resp.status_code}")
                    return wrapped
                else:
                    logger.warning(f"curl_cffi got {resp.status_code} for {url}")
                    return None
        except Exception as e:
            logger.warning(f"curl_cffi failed for {url}: {e}. Falling back to httpx.")

    # Fallback to httpx
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
