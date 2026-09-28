#!/usr/bin/env python
"""Rastreo inteligente de cifras y estadísticas en Google Drive con huella ligera.

Filtra candidatos por palabras clave en títulos de artículos y nombres de PDF antes
de descargar, descarga temporalmente, busca la cifra, guarda el rastro en `output/cifras_trace.json`
y elimina el archivo PDF inmediatamente para ahorrar espacio.

Uso:
    python smart_trace_cifras.py --cifra "26%" --keywords "tendero, tienda de barrio, supervivencia"
    python smart_trace_cifras.py --cifra "1.4%" --keywords "postal, mintic, contraprestacion"
    python smart_trace_cifras.py --cifra "48%" --keywords "informal, empleo"
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webapp.data import FenalcoData
from webapp.smart_cifras_crawler import SmartCifrasCrawler


def main():
    parser = argparse.ArgumentParser(description="Rastreador inteligente de cifras con descarga efímera")
    parser.add_argument("--cifra", type=str, required=True, help="Cifra o porcentaje a buscar (ej: '26%%', '1.4%%')")
    parser.add_argument("--keywords", type=str, default="", help="Palabras clave separadas por comas (ej: 'tendero, tienda de barrio, impuestos')")
    parser.add_argument("--limit", type=int, default=15, help="Límite máximo de nuevos PDFs a descargar e inspeccionar (def: 15)")
    parser.add_argument("--no-ocr", action="store_true", help="Desactivar OCR de gráficas/imágenes para mayor rapidez")
    args = parser.parse_args()

    print("=" * 70)
    print("  FENALCO · Rastreador Inteligente de Cifras (Huella Ligera)")
    print("=" * 70)

    cifra = args.cifra.strip()
    kws = [k.strip() for k in args.keywords.split(",") if k.strip()]

    print(f"Objetivo:      {cifra}")
    print(f"Filtro previo: {', '.join(kws) if kws else '(sin filtro, todos los adjuntos)'}")
    print(f"Límite nuevos: {args.limit} descargas efímeras")
    print(f"OCR gráficas:  {'Desactivado' if args.no_ocr else 'Activado'}")
    print("-" * 70)

    data = FenalcoData()
    data.reload()

    crawler = SmartCifrasCrawler(data)

    def progress_callback(curr, total, fname, status):
        print(f"[{curr}/{total}] {fname[:35]}... -> {status}")

    t0 = time.time()
    res = crawler.crawl_and_inspect(
        cifra_query=cifra,
        keywords=kws,
        max_downloads=args.limit,
        enable_ocr=not args.no_ocr,
        on_progress=progress_callback,
    )
    elapsed = time.time() - t0

    print("\n" + "=" * 70)
    print("RESULTADOS DEL RASTREO")
    print("=" * 70)
    print(f"Candidatos coincidentes con palabras clave: {res['candidates_found']}")
    print(f"Leídos de rastro previo / caché (0 MB bajados): {res['already_in_trace']}")
    print(f"Descargados, analizados y eliminados:        {res['newly_inspected']}")
    print(f"Coincidencias exactas con {cifra}:           {res['total_matches']}")
    print(f"Tiempo total:                                {elapsed:.1f} segundos")
    print("-" * 70)

    if not res["matches"]:
        print(f"No se encontró la cifra «{cifra}» en los documentos inspeccionados.")
    else:
        for idx, m in enumerate(res["matches"], 1):
            tag = "📊 GRÁFICA/OCR" if m["origin"] == "grafica" else "📄 PDF"
            source_info = f"[{'Rastro' if m.get('from_trace') else 'Nuevo'}]"
            print(f"\n{idx}. {tag} {source_info} {m['title']}")
            print(f"   Archivo: {m['filename']} | Fecha: {m.get('date', 'S/F')}")
            # Snippet sin tags html para terminal
            clean_snippet = m["snippet"].replace('<mark class="cifra-mark fw-bold text-dark px-1 rounded">', '>>> ').replace('</mark>', ' <<<')
            print(f"   Contexto: {clean_snippet}")
            if m.get("image"):
                print(f"   Imagen gráfica: {m['image']['src']} ({m['image']['caption']})")
            if m.get("drive_url"):
                print(f"   Enlace Drive:   {m['drive_url']}")

    print("\n" + "=" * 70)
    print("El rastro ha quedado almacenado en 'output/cifras_trace.json'.")
    print("La próxima vez que consultes este tema, responderá instantáneamente.")
    print("=" * 70)


if __name__ == "__main__":
    main()
