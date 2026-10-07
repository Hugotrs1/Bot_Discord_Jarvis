"""Requêtes HTTP. On se fait passer pour un navigateur, sinon beaucoup de sites refusent."""

import time

import aiohttp

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
TIMEOUT = aiohttp.ClientTimeout(total=20)


async def get_page(url):
    """Renvoie (code HTTP, contenu HTML)."""
    async with aiohttp.ClientSession(headers=HEADERS, timeout=TIMEOUT) as session:
        async with session.get(url) as response:
            return response.status, await response.text(errors="replace")


async def get_json(url, params=None):
    async with aiohttp.ClientSession(headers=HEADERS, timeout=TIMEOUT) as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json(content_type=None)


async def ping(url):
    """Teste un site. Renvoie (code HTTP ou None si aucune réponse, temps de réponse en ms)."""
    start = time.perf_counter()
    try:
        status, _ = await get_page(url)
    except (aiohttp.ClientError, TimeoutError):
        status = None
    return status, round((time.perf_counter() - start) * 1000)
