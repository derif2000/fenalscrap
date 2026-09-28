#!/usr/bin/env python
"""Indexador masivo de documentos adjuntos de Google Drive a disco local.

Descarga y extrae el texto de los PDFs y documentos de Google Drive asociados a las
publicaciones de FENALCO, guardándolos en `output/doc_cache/`.

Una vez guardados en disco:
1. El Buscador de Cifras y Estadísticas los escanea instantáneamente sin esperas.
2. El Asistente de IA tiene acceso inmediato a su contenido sin depender de descargas en vivo.

Uso:
    python pre_cache_attachments.py               # Procesa los primeros 50 pendientes
    python pre_cache_attachments.py --limit 200   # Procesa 200 pendientes
    python pre_cache_attachments.py --all         # Procesa todos los pendientes
    python pre_cache_attachments.py --ocr         # Activa además OCR sobre gráficas
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webapp.data import FenalcoData
from webapp.drive_reader import drive_reader, extract_drive_id, GENERIC_PRIVACY_IDS


def main():
    parser = argparse.ArgumentParser(description="Indexador masivo de adjuntos FENALCO a disco")
    parser.add_argument("--limit", type=int, default=50, help="Número de documentos a procesar (def: 50)")
    parser.add_argument("--all", action="store_true", help="Procesar todos los documentos pendientes")
    parser.add_argument("--ocr", action="store_true", help="Activar visión OCR para extraer datos de gráficas")
    parser.add_argument("--delay", type=float, default=1.0, help="Pausa en segundos entre descargas para no saturar Drive (def: 1.0s)")
    args = parser.parse_args()

    print("=" * 65)
    print("  FENALCO · Indexador Masivo de Documentos Adjuntos")
    print("=" * 65)

    data = FenalcoData()
    data.reload()

    # Recolectar todos los adjuntos únicos de los 4.000 registros
    seen_ids = set()
    pending = []

    for r in data.records:
        for doc in r.get("documents") or []:
            u = doc.get("url") or ""
            did = extract_drive_id(u)
            if not did or did in seen_ids or did in GENERIC_PRIVACY_IDS:
                continue
            seen_ids.add(did)
            if not drive_reader.is_cached(did):
                pending.append({
                    "doc_id": did,
                    "url": u,
                    "filename": doc.get("filename") or "Documento",
                    "article_title": r.get("title") or "",
                })

    cached_count = len(seen_ids) - len(pending)
    print(f"Total documentos detectados: {len(seen_ids):,}")
    print(f"Ya guardados en disco (doc_cache): {cached_count:,}")
    print(f"Pendientes de descargar e indexar: {len(pending):,}")
    print("-" * 65)

    if not pending:
        print("✅ ¡Todos los documentos ya están indexados en output/doc_cache/!")
        return

    to_process = pending if args.all else pending[:args.limit]
    print(f"Iniciando indexación de {len(to_process):,} documentos (OCR={'activado' if args.ocr else 'desactivado'})...\n")

    success = 0
    errors = 0
    t0 = time.time()

    for idx, item in enumerate(to_process, 1):
        did = item["doc_id"]
        fname = item["filename"][:35]
        print(f"[{idx}/{len(to_process)}] Indexando «{fname}» ({did[:10]}…)...", end="", flush=True)

        try:
            txt = drive_reader.download_and_extract(
                item["url"],
                timeout=30.0,
                enable_ocr=args.ocr,
            )
            if txt and len(txt) > 20:
                success += 1
                print(f" OK ({len(txt):,} caracteres)")
            else:
                errors += 1
                print(" VACÍO / PROTEGIDO")
        except Exception as e:
            errors += 1
            print(f" ERROR: {e}")

        if args.delay > 0:
            time.sleep(args.delay)

    elapsed = time.time() - t0
    print("\n" + "=" * 65)
    print(f"Resumen de indexación en {elapsed:.1f} segundos:")
    print(f"  • Indexados exitosamente: {success}")
    print(f"  • Errores / Sin texto:     {errors}")
    print(f"  • Total en disco ahora:    {cached_count + success:,} de {len(seen_ids):,}")
    print("=" * 65)
    print("Ahora puedes buscar cualquier cifra en el 'Buscador de Cifras y Estadísticas'.")


if __name__ == "__main__":
    main()
