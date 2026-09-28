"""Descarga y parsea el sitemap de FENALCO, clasificando cada URL."""

import xml.etree.ElementTree as ET
from pathlib import Path

from . import config

_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def fetch_sitemap(session=None, force: bool = False) -> Path:
    """Descarga el sitemap.xml y lo guarda localmente. Devuelve la ruta."""
    path = config.SITEMAP_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return path

    import requests
    if session is None:
        session = requests.Session()
    resp = session.get(config.SITEMAP_URL, timeout=config.TIMEOUT)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    print(f"[sitemap] Descargado ({len(resp.content)} bytes) -> {path}")
    return path


def parse_sitemap(path: Path = None) -> list[dict]:
    """Lee el sitemap y devuelve una lista de dicts:
    {"url", "lastmod", "rel", "kind", "category"}."""
    path = path or config.SITEMAP_FILE
    tree = ET.parse(path)
    entries = []
    for el in tree.getroot().findall("sm:url", _NS):
        loc = (el.findtext("sm:loc", namespaces=_NS) or "").strip()
        lastmod = (el.findtext("sm:lastmod", namespaces=_NS) or "").strip()
        if not loc:
            continue
        entries.append(_annotate(loc, lastmod))
    return entries


def _annotate(url: str, lastmod: str = "") -> dict:
    rel = url.replace(config.SITE, "").strip("/")

    if "/blog/" in "/" + rel:
        parts = rel.split("/")
        idx = parts.index("blog")
        cat_id = parts[idx + 1] if len(parts) > idx + 1 else ""
        # Un post real tiene la forma blog/<categoria>/<slug>-<id>: al menos
        # 4 segmentos (2 antes del slug-id). Los listados/feeds no lo cumplen.
        is_post = bool(parts[-1]) and parts[-1].split("-")[-1].isdigit() \
            and len(parts) > idx + 2
        kind = "blog-post" if is_post else "blog-listing"
        category = config.BLOG_CATEGORIES.get(cat_id, cat_id or "Blog")
    elif rel.startswith("event/"):
        kind = "event"
        category = "Eventos"
    elif rel.startswith("blog"):
        kind = "blog-listing"
        category = "Blog"
    elif rel in ("",):
        kind = "cms"
        category = "Inicio"
    elif rel.startswith(("profile", "website/", "appointment", "calendar",
                         "shop", "slides", "helpdesk", "event/register")):
        kind = "aux"
        category = rel.split("/")[0]
    else:
        # Páginas CMS individuales (el-gremio, formacion, seccionales, etc.)
        kind = "cms"
        category = rel.split("/")[0]

    return {
        "url": url,
        "lastmod": lastmod,
        "rel": rel,
        "kind": kind,
        "category": category,
    }


def load_or_fetch_urls(session=None, force_sitemap=False) -> list[dict]:
    """Obtiene la lista anotada de URLs (descargando el sitemap si hace falta)."""
    fetch_sitemap(session, force=force_sitemap)
    return parse_sitemap()


def save_list(entries: list[dict]) -> None:
    """Guarda las listas de URLs en data/ para referencia."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    posts = [e for e in entries if e["kind"] == "blog-post"]
    others = [e for e in entries if e["kind"] != "blog-post"]
    config.URLS_FILE.write_text(
        "\n".join(e["url"] for e in sorted(entries, key=lambda x: x["url"])),
        encoding="utf-8")
    config.CMS_URLS_FILE.write_text(
        "\n".join(e["url"] for e in sorted(others, key=lambda x: x["url"])),
        encoding="utf-8")
    print(f"[sitemap] {len(entries)} URLs -> {len(posts)} blog posts, "
          f"{len(entries) - len(posts)} otros")
