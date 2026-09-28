"""Verificador de actualizaciones del sitio de FENALCO.

Compara el sitemap oficial actual con los datos ya almacenados y detecta
nuevas páginas, modificaciones y publicaciones retiradas. Permite descargar
los contenidos nuevos y refrescar la aplicación.
"""

import re
import threading
import time

from fenalco_scraper import sitemap
from fenalco_scraper.crawler import FenalcoScraper
from fenalco_scraper import export
from fenalco_scraper import config

from .data import FenalcoData


def _normalize_url(url: str) -> str:
    """Normaliza una URL para comparar páginas que redirigen.

    Las páginas de eventos, al guardarse, quedan con la URL final (p. ej.
    /event/x/register, /event/x/track/..., /event/x/page/introduccion-...),
    mientras el sitemap conserva la canónica (/event/x-<id>). Esta función
    reduce cada URL a una forma comparable.
    """
    u = (url or "").split("?")[0].split("#")[0].rstrip("/")
    # Para eventos, conservar solo hasta el '...-<id>' y descartar sufijos.
    u = re.sub(r"/event/(.+?-\d+)(?:/.*)?$", r"/event/\1", u)
    return u


class UpdateVerifier:
    """Comprueba novedades y coordina la descarga de contenido nuevo."""

    # Tipos de página que NO se procesan (auxiliares / listados)
    IGNORE_KINDS = ("aux", "blog-listing")

    def __init__(self, data: FenalcoData):
        self.data = data
        self.last_check = None          # último dict de resultados
        self.last_check_time = None     # timestamp
        self._lock = threading.Lock()
        self._busy = threading.Lock()   # evita descargas simultáneas

    # ------------------------------------------------------------ detección
    def check(self, force_sitemap: bool = True) -> dict:
        """Obtiene el sitemap actual y compara con los datos locales."""
        with self._lock:
            entries = sitemap.load_or_fetch_urls(force_sitemap=force_sitemap)
            content = [e for e in entries if e["kind"] not in self.IGNORE_KINDS]
            existing = {u: r for u, r in self.data.by_url.items()}
            # Mapa URL-normalizada -> registro local
            by_norm = {}
            for _u, rec in existing.items():
                by_norm.setdefault(_normalize_url(_u), []).append(rec)
            content_norm = {_normalize_url(e["url"]) for e in content}

            new = []
            modified = []
            for e in content:
                key = _normalize_url(e["url"])
                local = by_norm.get(key)
                if not local:
                    new.append(e)
                else:
                    rec = local[0]
                    if (e.get("lastmod") and rec.get("lastmod")
                            and e["lastmod"] != rec.get("lastmod")):
                        modified.append({**e, "old_lastmod": rec.get("lastmod", "")})

            deleted = [u for u in existing if _normalize_url(u) not in content_norm]

            self.last_check = {
                "new": new,
                "modified": modified,
                "deleted": deleted,
                "total_sitemap": len(entries),
                "content_count": len(content),
            }
            self.last_check_time = time.strftime("%Y-%m-%d %H:%M:%S")
            return self.last_check

    @property
    def is_busy(self) -> bool:
        return self._busy.locked()

    # ------------------------------------------------------------- descarga
    def scrape_new(self, entries_new: list, workers: int = None) -> dict:
        """Descarga el contenido nuevo, regenera los archivos y refresca la app."""
        if not entries_new:
            return {"ok": 0, "errors": 0, "msg": "No hay contenido nuevo."}
        if not self._busy.acquire(blocking=False):
            return {"ok": 0, "errors": 0,
                    "msg": "Ya hay una descarga en curso. Espera a que termine."}

        try:
            scraper = FenalcoScraper(workers=workers or config.DEFAULT_WORKERS,
                                     delay=config.DEFAULT_DELAY, resume=True)
            scraper.run(entries_new, limit=0)
            export.export()
            self.data.reload()
            return {"ok": len([e for e in entries_new]),
                    "errors": scraper._errors,
                    "msg": f"Descargadas {len(entries_new)} páginas nuevas."}
        finally:
            self._busy.release()


def build_result_panel(result: dict, collapse_id: str = None):
    """Convierte el resultado del chequeo en (html, n_nuevos)."""
    import dash_bootstrap_components as dbc
    from dash import html

    if result is None:
        return None, 0

    new = result.get("new", [])
    mod = result.get("modified", [])
    deleted = result.get("deleted", [])
    total = result.get("content_count", 0)

    rows = []
    for e in new[:50]:
        rows.append(html.Tr([
            html.Td(html.A(kind_label(e["kind"]), href=e["url"], target="_blank")),
            html.Td(e.get("category", "")),
            html.Td(html.A(e["url"], href=e["url"], target="_blank",
                           className="text-break")),
        ]))
    if len(new) > 50:
        rows.append(html.Tr([
            html.Td(f"... y {len(new) - 50} más", colSpan=3,
                    className="text-muted")]))

    if new:
        table = dbc.Table([
            html.Thead(html.Tr([html.Th("Tipo"), html.Th("Categoría"),
                                html.Th("Enlace")])),
            html.Tbody(rows),
        ], size="sm", bordered=True, striped=True, className="mb-0")
    else:
        table = html.P("Sin páginas nuevas.", className="text-muted mb-0")

    # Encabezado del panel con el botón para contraer/expandir
    collapse_btn = html.Span()
    if collapse_id:
        collapse_btn = dbc.Button(
            [html.I(className="bi bi-chevron-up me-1"),
             html.Span("Contraer", className="d-none d-sm-inline")],
            id=collapse_id, size="sm", color="secondary", outline=True,
            n_clicks=0, title="Contraer este panel",
        )

    header = dbc.CardHeader(dbc.Row([
        dbc.Col([
            html.Span("Resultado de la comprobación", className="fw-bold me-2"),
            dbc.Badge(f"Nuevas: {len(new)}", color="success", className="me-1"),
            dbc.Badge(f"Modificadas: {len(mod)}", color="warning", className="me-1"),
            dbc.Badge(f"Retiradas: {len(deleted)}", color="secondary"),
        ], className="align-self-center"),
        dbc.Col([collapse_btn], className="text-end align-self-center"),
    ], className="g-2 align-items-center"))

    panel = dbc.Card([
        header,
        dbc.CardBody([
            html.P(f"El sitio tiene {total} páginas de contenido.",
                   className="small text-muted"),
            table,
        ]),
    ], className="border-0 bg-light shadow-sm")

    return panel, len(new)


def kind_label(kind: str) -> str:
    return {"blog-post": "Blog", "cms": "Página", "event": "Evento"}.get(kind, kind)
