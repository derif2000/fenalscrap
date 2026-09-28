#!/usr/bin/env python
"""Punto de entrada del scraper de FENALCO.

Uso:
    python run.py                     # scrapea todo el sitio
    python run.py --limit 20          # prueba con 20 páginas
    python run.py --only cms          # solo páginas CMS
    python run.py --workers 4 --delay 0.3
    python run.py --no-resume         # ignora el checkpoint previo
"""
import argparse
import sys
from pathlib import Path

# Garantizar que el paquete src/ sea importable
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fenalco_scraper import config, sitemap            # noqa: E402
from fenalco_scraper.crawler import FenalcoScraper     # noqa: E402


def main():
    p = argparse.ArgumentParser(description="Extrae los datos públicos de fenalco.com.co")
    p.add_argument("--limit", type=int, default=0,
                   help="Máximo de páginas a procesar (0 = todas)")
    p.add_argument("--only", choices=["blog", "cms", "event", "aux"],
                   default=None, help="Procesar solo un tipo de página")
    p.add_argument("--workers", type=int, default=config.DEFAULT_WORKERS)
    p.add_argument("--delay", type=float, default=config.DEFAULT_DELAY)
    p.add_argument("--no-resume", action="store_true",
                   help="Ignorar el checkpoint y volver a scrapear todo")
    p.add_argument("--include-aux", action="store_true",
                   help="Incluir páginas auxiliares (profile, shop, helpdesk, "
                        "slides, blog-listing) que suelen requerir login")
    p.add_argument("--fresh-sitemap", action="store_true",
                   help="Redescargar el sitemap.xml")
    args = p.parse_args()

    entries = sitemap.load_or_fetch_urls(force_sitemap=args.fresh_sitemap)
    sitemap.save_list(entries)

    if args.only:
        entries = [e for e in entries if e["kind"] == args.only]
    elif not args.include_aux:
        # Por defecto: contenido editorial (posts, CMS, eventos).
        # Las páginas auxiliares (perfil/login, shop, helpdesk, listados del
        # blog, etc.) no aportan datos públicos y suelen redirigir al login.
        entries = [e for e in entries
                   if e["kind"] not in ("aux", "blog-listing")]

    if not entries:
        print("No hay URLs para procesar. Revisa --only.")
        return

    # Mostrar un resumen por tipo
    from collections import Counter
    for k, v in Counter(e["kind"] for e in entries).most_common():
        print(f"  {v:5d}  {k}")

    scraper = FenalcoScraper(workers=args.workers, delay=args.delay,
                             resume=not args.no_resume)
    scraper.run(entries, limit=args.limit)


if __name__ == "__main__":
    main()
