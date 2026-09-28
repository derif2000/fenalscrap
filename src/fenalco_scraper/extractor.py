"""Convierte el HTML de cada página de FENALCO en un registro estructurado."""

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import config

# Elementos que nunca son contenido editorial
_NON_CONTENT = [
    "script", "style", "noscript", "template", "iframe",
    "header", "footer", "nav",
]


def _drop_noise(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(_NON_CONTENT):
        tag.decompose()
    for sel in [".o_footer", ".js_cookie-policy-banner", ".o_collapse_apps",
                ".oe_removable", ".modal", ".d-none", ".invisible",
                ".o_wevent_registration", ".nav-login", ".o_website_login"]:
        for el in soup.select(sel):
            el.decompose()
    for el in soup.select("button, form, input[type=hidden]"):
        el.decompose()


def _content_root(soup: BeautifulSoup, kind: str):
    """Devuelve el elemento (Tag) que contiene el cuerpo del contenido."""
    if kind == "blog-post":
        js_blog = soup.select_one(".js_blog.website_blog")
        if js_blog:
            cands = js_blog.select("section.container, .o_wblog_post, .blog_post")
            if cands:
                return max(cands, key=lambda c: len(c.get_text(" ", strip=True)))
            return js_blog
    if kind == "event":
        ev = soup.select_one(".o_wevent_event") or soup.select_one(".o_website_event")
        if ev:
            return ev

    # CMS y resto: el mayor bloque de texto dentro de <main>
    main = soup.select_one("main") or soup.find("body")
    oe = [o for o in soup.select("main .oe_structure")
          if len(o.get_text(" ", strip=True)) > 0]
    if oe:
        return max(oe, key=lambda o: len(o.get_text(" ", strip=True)))

    best = (0, None)
    for d in main.find_all(["div", "section", "article"]):
        if d.find_parent(["header", "footer", "nav"]):
            continue
        n = len(d.get_text("\n", strip=True))
        if n > best[0]:
            best = (n, d)
    container = best[1] if best[1] is not None else main
    children = [c for c in container.find_all(recursive=False)
                if c.get_text(" ", strip=True)]
    if children:
        sub = max(children, key=lambda c: len(c.get_text(" ", strip=True)))
        if best[0] and len(sub.get_text("\n", strip=True)) / best[0] > 0.85:
            container = sub
    return container

def _walk_blocks(root, blocks: list) -> None:
    """Recorre los elementos de bloque del contenido y genera bloques."""
    for child in root.children:
        if getattr(child, "name", None) is None:
            continue  # texto suelto / comentario

        tag = child.name.lower()
        if tag in ("script", "style"):
            continue

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = " ".join(child.get_text(" ", strip=True).split())
            if text:
                blocks.append({"type": "heading", "level": int(tag[1]),
                               "text": text})
        elif tag in ("ul", "ol"):
            items = []
            for li in child.find_all("li", recursive=False):
                t = " ".join(li.get_text(" ", strip=True).split())
                if t:
                    items.append(t)
            if items:
                blocks.append({"type": "list", "ordered": tag == "ol",
                               "items": items})
        elif tag == "figure":
            img = child.find("img")
            cap = child.find("figcaption")
            blocks.append({
                "type": "image",
                "src": (img["src"] if img and img.get("src") else ""),
                "alt": (img.get("alt") if img else "") or "",
                "caption": " ".join(cap.get_text(" ", strip=True).split())
                if cap else "",
            })
        elif tag == "img":
            if child.get("src"):
                blocks.append({"type": "image", "src": child["src"],
                               "alt": child.get("alt") or ""})
        elif tag == "blockquote":
            text = " ".join(child.get_text(" ", strip=True).split())
            if text:
                blocks.append({"type": "quote", "text": text})
        elif tag == "table":
            rows = []
            for tr in child.find_all("tr"):
                cells = [" ".join(c.get_text(" ", strip=True).split())
                         for c in tr.find_all(["td", "th"])]
                cells = [c for c in cells if c]
                if cells:
                    rows.append(cells)
            if rows:
                blocks.append({"type": "table", "rows": rows})
        elif tag in ("div", "section", "article"):
            _walk_blocks(child, blocks)
        elif tag in ("p", "span", "li", "td", "label", "strong", "em",
                     "center", "font"):
            text = " ".join(child.get_text(" ", strip=True).split())
            if text:
                blocks.append({"type": "paragraph", "text": text})
        elif tag == "hr":
            continue
        else:
            text = " ".join(child.get_text(" ", strip=True).split())
            if text and len(text) > 2:
                blocks.append({"type": "paragraph", "text": text})


def _extract_title(soup: BeautifulSoup) -> str:
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        return og["content"].strip()
    h1 = soup.select_one("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(" ", strip=True).strip()
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True).strip()
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    og = soup.select_one('meta[property="og:description"]')
    if og and og.get("content"):
        return og["content"].strip()
    m = soup.select_one('meta[name="description"]')
    if m and m.get("content"):
        return m["content"].strip()
    return ""


def _extract_image(soup: BeautifulSoup) -> str:
    og = soup.select_one('meta[property="og:image"]')
    if og and og.get("content"):
        return og["content"].strip()
    img = soup.select_one("main img")
    if img and img.get("src"):
        return img["src"]
    return ""


def _extract_date(soup: BeautifulSoup, fallback: str = "") -> str:
    t = soup.select_one("time[datetime]")
    if t and t.get("datetime"):
        return t["datetime"].split("T")[0].split(" ")[0]
    m = soup.select_one('meta[property="article:published_time"], '
                        'meta[name="pubdate"], meta[itemprop="datePublished"]')
    if m and m.get("content"):
        return m["content"].split("T")[0].split(" ")[0]
    return fallback or ""


def _collect_images(soup: BeautifulSoup, container) -> list:
    out = []
    for img in container.find_all("img"):
        src = (img.get("src") or img.get("data-src")
               or img.get("data-original"))
        if src and src not in out:
            out.append(src)
    return out


def _collect_documents(soup: BeautifulSoup, container, base_url: str) -> list:
    """Detecta enlaces a documentos/descargables y adjuntos de Odoo."""
    docs = []
    for a in container.find_all("a", href=True):
        href = a["href"].strip()
        low = href.lower()
        text = " ".join(a.get_text(" ", strip=True)).strip()
        text_low = text.lower()
        is_attachment = (
            low.endswith(config.DOC_EXTENSIONS)
            or "/web/content/" in low
            or "download" in low
            or "/web/image/" in low
            or "drive.google.com" in low
            or "docs.google.com" in low
            or ("descarg" in text_low and low.startswith("http"))
            or ("documento" in text_low and low.startswith("http"))
        )
        if is_attachment:
            full = urljoin(base_url, href)
            entry = {"url": full, "filename": text or full.split("/")[-1]}
            if entry not in docs:
                docs.append(entry)
    return docs


def _extract_drive_id(url: str) -> str:
    """Extrae el id de archivo de una URL de Google Drive."""
    import re
    m = re.search(r"/file/d/([^/?#]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"[?&]id=([^&#]+)", url)
    if m:
        return m.group(1)
    return ""


def _collect_embedded_docs(soup: BeautifulSoup) -> list:
    """Detecta documentos embebidos en <iframe> (p. ej. Google Drive).

    Debe llamarse ANTES de eliminar los iframes de la limpieza de ruido.
    """
    docs = []
    for frame in soup.find_all("iframe"):
        src = frame.get("src") or frame.get("data-src") or ""
        if not src:
            continue
        src = src.strip()
        low = src.lower()

        drive_id = ""
        if "drive.google.com" in low or "docs.google.com" in low:
            drive_id = _extract_drive_id(src)

        known_host = (
            "drive.google.com" in low
            or "docs.google.com" in low
            or "onedrive" in low
            or "1drv.ms" in low
            or "dropbox.com" in low
            or "/webcontent" in low
        )

        if drive_id:
            docs.append({
                "url": f"https://drive.google.com/file/d/{drive_id}/view",
                "filename": "Documento embebido (Google Drive)",
                "embed_url": src,
                "drive_id": drive_id,
            })
        elif known_host:
            host = "Google Drive" if ("google" in low) else (
                   "OneDrive" if ("onedrive" in low or "1drv.ms" in low)
                   else "Dropbox" if "dropbox" in low else "incrustado")
            docs.append({
                "url": src,
                "filename": f"Documento embebido ({host})",
                "embed_url": src,
            })

    out, seen = [], set()
    for d in docs:
        if d["url"] not in seen:
            seen.add(d["url"])
            out.append(d)
    return out


def _collect_links(soup: BeautifulSoup, container, base_url: str) -> list:
    links = []
    for a in container.find_all("a", href=True):
        href = a["href"].strip()
        text = " ".join(a.get_text(" ", strip=True).split())
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        links.append({"url": urljoin(base_url, href), "text": text})
    return links




def _blocks_to_text(blocks: list) -> str:
    lines = []
    for b in blocks:
        if b["type"] == "heading":
            lines.append("#" * b["level"] + " " + b["text"])
        elif b["type"] in ("paragraph", "quote"):
            lines.append(b["text"])
        elif b["type"] == "list":
            mark = "- " if not b["ordered"] else "1. "
            lines += [mark + it for it in b["items"]]
        elif b["type"] == "table":
            lines.append(" | ".join(" / ".join(r) for r in b["rows"]))
    return "\n".join(lines)


def extract_page(html: str, url: str, *, kind: str = "cms",
                 category: str = "", lastmod: str = "") -> dict:
    """Extrae un registro estructurado a partir del HTML de una página."""
    soup = BeautifulSoup(html, "lxml")
    # Capturar documentos embebidos (iframe) ANTES de eliminar el ruido.
    embeds = _collect_embedded_docs(soup)
    _drop_noise(soup)

    root = _content_root(soup, kind) or soup
    blocks: list = []
    _walk_blocks(root, blocks)

    docs = _collect_documents(soup, root, url)
    seen = {d["url"] for d in docs}
    for e in embeds:
        key = e.get("url") or e.get("embed_url") or ""
        if key and key not in seen:
            docs.append({"url": e["url"], "filename": e["filename"]})
            seen.add(key)

    return {
        "url": url,
        "kind": kind,
        "category": category,
        "title": _extract_title(soup),
        "subtitle": _extract_description(soup),
        "publish_date": _extract_date(soup, fallback=lastmod),
        "lastmod": lastmod,
        "image": _extract_image(soup),
        "content_blocks": blocks,
        "content_text": _blocks_to_text(blocks).strip(),
        "images": _collect_images(soup, root),
        "documents": docs,
        "links": _collect_links(soup, root, url),
    }

