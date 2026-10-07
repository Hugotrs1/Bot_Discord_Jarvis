"""Petites fonctions pour faire des requêtes HTTP.

On se présente comme un vrai navigateur (« User-Agent ») : beaucoup de sites
refusent sinon de répondre aux programmes.
"""

import time

import aiohttp

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

# On abandonne une requête au bout de 20 secondes
TIMEOUT = aiohttp.ClientTimeout(total=20)

# Erreurs « normales » quand un site ne répond pas : on les attrape dans les modules
NETWORK_ERRORS = (aiohttp.ClientError, TimeoutError)


async def download_page(url: str) -> tuple[int, str]:
    """Télécharge une page. Renvoie (code HTTP, contenu HTML)."""
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS, timeout=TIMEOUT) as session:
        async with session.get(url) as response:
            html = await response.text(errors="replace")
            return response.status, html


async def download_json(url: str, params: dict | None = None) -> dict:
    """Appelle une API et renvoie sa réponse JSON. Lève une erreur si le code HTTP est mauvais."""
    async with aiohttp.ClientSession(headers=BROWSER_HEADERS, timeout=TIMEOUT) as session:
        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.json(content_type=None)


async def check_website(url: str) -> tuple[bool, int | None, int]:
    """Teste si un site répond.

    Renvoie (en ligne ?, code HTTP ou None si aucune réponse, temps de réponse en millisecondes).
    Un site est considéré en ligne si son code HTTP est inférieur à 400 (200 = OK, 404 = introuvable…).
    """
    start = time.perf_counter()
    try:
        status, _ = await download_page(url)
    except NETWORK_ERRORS:
        status = None
    elapsed_ms = round((time.perf_counter() - start) * 1000)

    is_online = status is not None and status < 400
    return is_online, status, elapsed_ms
