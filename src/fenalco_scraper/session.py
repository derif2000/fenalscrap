"""Sesión HTTP reutilizable con reintentos y cabeceras de navegador."""

import random
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


def build_session() -> requests.Session:
    """Crea una sesión de requests con retry adapters y User-Agent de navegador."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    })

    retry = Retry(
        total=config.MAX_RETRIES,
        backoff_factor=config.RETRY_BACKOFF,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def polite_sleep(base: float = None) -> None:
    """Pausa corta antes de la siguiente petición (cortesía al servidor)."""
    base = config.DEFAULT_DELAY if base is None else base
    time.sleep(base * random.uniform(0.7, 1.6))


def fetch_html(session: requests.Session, url: str):
    """Descarga una URL y devuelve (texto_html, status_code).

    Si el servidor redirige a la página de login, se devuelve el texto
    redirigido; el llamador decide si le sirve.
    """
    resp = session.get(url, timeout=config.TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    # Confiar en el charset declarado; si no hay, forzar utf-8.
    if resp.encoding and resp.encoding.lower() not in ("utf-8", "utf8"):
        if not resp.apparent_encoding:
            resp.encoding = "utf-8"
    else:
        resp.encoding = "utf-8"
    return resp.text, resp.status_code, resp.url
