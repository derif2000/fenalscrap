"""Rastreador inteligente de cifras en documentos de Google Drive con huella ligera.

1. Filtra previamente los documentos por palabras clave en títulos de artículos y nombres de archivo.
2. Descarga temporalmente los documentos candidatos.
3. Extrae y busca la cifra requerida.
4. Guarda un rastro ligero (extractos y porcentajes encontrados) en `output/cifras_trace.json`.
5. Elimina inmediatamente el archivo PDF descargado para ahorrar espacio en disco.
6. Si un documento ya fue rastreado antes, lee directamente del rastro sin volver a descargarlo.
"""

import json
import logging
import os
import re
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .cifras_search import parse_cifra_query, _extract_snippet
from .drive_reader import (
    GENERIC_PRIVACY_IDS,
    IMAGE_MARKER_RE,
    _CACHE_DIR,
    _IMGS_DIR,
    clean_spaced_name,
    drive_reader,
    extract_drive_id,
)

logger = logging.getLogger("fenalco.smart_cifras_crawler")

_TRACE_FILE = Path(__file__).resolve().parents[2] / "output" / "cifras_trace.json"


def _norm(text: str) -> str:
    """Normaliza texto para comparación insensible a mayúsculas y acentos."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower().strip()


class SmartCifrasCrawler:
    """Rastreador de cifras con descarga efímera y almacenamiento de rastro ligero."""

    def __init__(self, data_store):
        self.store = data_store
        self.trace_file = _TRACE_FILE
        self._trace_cache = self._load_trace()

    def _load_trace(self) -> Dict[str, Any]:
        """Carga el índice histórico de rastros ligeros."""
        if self.trace_file.exists():
            try:
                return json.loads(self.trace_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"No se pudo cargar cifras_trace.json: {e}")
        return {}

    def _save_trace(self):
        """Guarda el índice ligero en disco de forma atómica."""
        self.trace_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp = self.trace_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._trace_cache, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.trace_file)
        except Exception as e:
            logger.error(f"Error guardando cifras_trace.json: {e}")

    def cleanup_expired_cache(self, ttl_hours: float = 24.0):
        """Elimina archivos en doc_cache que tengan más de 24 horas (1 día) desde su descarga."""
        if not _CACHE_DIR.exists():
            return
        cutoff = time.time() - (ttl_hours * 3600)
        cleaned = 0
        for f in _CACHE_DIR.glob("*.txt"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    cleaned += 1
            except Exception:
                pass
        if cleaned > 0:
            logger.info(f"Limpieza de caché: eliminados {cleaned} archivo(s) anteriores a {ttl_hours}h")

    def filter_candidates(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """Selecciona únicamente los documentos cuyos títulos o artículos coincidan con las palabras clave.

        Args:
            keywords: lista de palabras clave (ej: ['tendero', 'tienda de barrio', 'impuestos']).

        Returns:
            Lista de documentos candidatos con metadatos.
        """
        norm_kws = [_norm(k) for k in keywords if len(_norm(k)) >= 2]
        seen_ids = set()
        candidates = []

        for r in self.store.records:
            art_title = r.get("title") or ""
            art_sub = r.get("subtitle") or ""
            art_cat = r.get("category") or ""
            full_meta = f"{art_title} {art_sub} {art_cat}"
            norm_meta = _norm(full_meta)

            for doc in r.get("documents") or []:
                u = doc.get("url") or ""
                did = extract_drive_id(u)
                if not did or did in seen_ids or did in GENERIC_PRIVACY_IDS:
                    continue

                fn = doc.get("filename") or ""
                norm_fn = _norm(clean_spaced_name(fn))
                searchable = f"{norm_meta} {norm_fn}"

                # Si no se dieron palabras clave, incluye todos; si se dieron, verifica coincidencia
                match = True
                if norm_kws:
                    match = any(kw in searchable for kw in norm_kws)

                if match:
                    seen_ids.add(did)
                    candidates.append({
                        "doc_id": did,
                        "url": u,
                        "filename": clean_spaced_name(fn) or "Documento adjunto",
                        "article_title": art_title,
                        "article_url": r.get("url") or "",
                        "publish_date": r.get("publish_date") or "",
                        "category": art_cat,
                    })

        return candidates

    def crawl_and_inspect(
        self,
        cifra_query: str,
        keywords: Optional[List[str]] = None,
        max_downloads: int = 25,
        enable_ocr: bool = True,
        on_progress=None,
    ) -> Dict[str, Any]:
        """Ejecuta el rastreo inteligente: filtra, consulta rastro o descarga, analiza, limpia y guarda rastro.

        Args:
            cifra_query: La cifra a buscar (ej: '26%', '1.4%', '550').
            keywords: Palabras clave opcionales para acotar los candidatos.
            max_downloads: Máximo de archivos nuevos a descargar y analizar en esta pasada.
            enable_ocr: Si es True, analiza también gráficas y tablas mediante OCR.
            on_progress: Callback opcional (actual, total, nombre_archivo, status).

        Returns:
            Dict con estadísticas y lista de coincidencias con fragmentos.
        """
        patterns, query_kws, label = parse_cifra_query(cifra_query)
        kw_list = keywords or []
        candidates = self.filter_candidates(kw_list)

        # Depurar archivos descargados que tengan más de 24 horas (1 día)
        self.cleanup_expired_cache(24.0)

        matches = []
        already_cached = 0
        newly_processed = 0
        errors = 0

        # Para cada candidato, revisar si ya está en el rastro ligero o en la caché existente
        for idx, cand in enumerate(candidates, 1):
            did = cand["doc_id"]
            trace_entry = self._trace_cache.get(did)

            doc_text = ""
            is_from_trace = False

            # Caso 1: Ya existe en el rastro ligero histórico
            if trace_entry:
                is_from_trace = True
                already_cached += 1
                # Comprobar si la cifra buscada coincide con algún extracto guardado o con los porcentajes registrados
                doc_text = trace_entry.get("full_text_compact", "")
                if on_progress:
                    on_progress(idx, len(candidates), cand["filename"], "Desde rastro previo (sin descargar)")
            else:
                # Caso 2: Verificar si ya existe en output/doc_cache/
                if drive_reader.is_cached(did):
                    cached_txt = drive_reader.get_cached_text(did) or ""
                    doc_text = cached_txt
                    already_cached += 1
                    if on_progress:
                        on_progress(idx, len(candidates), cand["filename"], "Desde caché local (sin descargar)")
                else:
                    # Caso 3: Descargar temporalmente, extraer, guardar rastro y BORRAR
                    if newly_processed >= max_downloads:
                        continue

                    if on_progress:
                        on_progress(idx, len(candidates), cand["filename"], "Descargando e inspeccionando…")

                    try:
                        # Extraer texto (drive_reader descarga a caché)
                        extracted = drive_reader.download_and_extract(
                            cand["url"],
                            timeout=35.0,
                            enable_ocr=enable_ocr,
                        )
                        doc_text = extracted or ""
                        newly_processed += 1

                        # Crear entrada de rastro ligero
                        pcts_in_doc = list(set(re.findall(r"\b\d+(?:[.,]\d+)?\s*(?:%|por\s*ciento\b)", doc_text, re.IGNORECASE)))
                        self._trace_cache[did] = {
                            "doc_id": did,
                            "filename": cand["filename"],
                            "article_title": cand["article_title"],
                            "article_url": cand["article_url"],
                            "category": cand["category"],
                            "publish_date": cand["publish_date"],
                            "analyzed_at": datetime.now().isoformat(),
                            "percentages_found": pcts_in_doc[:60],
                            "full_text_compact": doc_text[:120000],  # Guarda texto compacto para rastreos futuros
                        }
                        self._save_trace()

                        # Retención de 1 día (24 horas): el archivo se conserva en _CACHE_DIR
                        # para permitir consultas rápidas durante el día y se depura cuando expire.
                        pass

                    except Exception as e:
                        errors += 1
                        logger.warning(f"Error procesando {did}: {e}")
                        continue

            # Buscar la cifra en el texto del documento
            if doc_text and patterns:
                ocr_sep = "--- [DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF] ---"
                has_ocr = ocr_sep in doc_text
                ocr_pos = doc_text.find(ocr_sep) if has_ocr else len(doc_text)

                for pat in patterns:
                    m = pat.search(doc_text)
                    if m:
                        m_pos = m.start()
                        is_ocr = has_ocr and m_pos > ocr_pos
                        snippet = _extract_snippet(doc_text, m)

                        img_data = None
                        if is_ocr:
                            img_matches = list(IMAGE_MARKER_RE.finditer(doc_text))
                            if img_matches:
                                closest = min(img_matches, key=lambda im: abs(im.start() - m_pos))
                                img_data = {
                                    "src": closest.group("src"),
                                    "caption": closest.group("caption") or "Gráfica / Tabla extraída",
                                }

                        matches.append({
                            "doc_id": did,
                            "origin": "grafica" if is_ocr else "documento",
                            "origin_label": "Gráfica / Tabla (OCR)" if is_ocr else "Documento PDF",
                            "badge_color": "warning" if is_ocr else "info",
                            "icon": "bar-chart-fill" if is_ocr else "file-earmark-pdf-fill",
                            "title": cand["article_title"] or cand["filename"],
                            "filename": cand["filename"],
                            "date": cand["publish_date"],
                            "category": cand["category"],
                            "url": cand["article_url"],
                            "drive_url": f"https://drive.google.com/file/d/{did}/view",
                            "snippet": snippet,
                            "image": img_data,
                            "from_trace": is_from_trace,
                        })
                        break

        # Ordenar coincidencias por fecha
        matches.sort(key=lambda x: str(x.get("date") or ""), reverse=True)

        return {
            "query_cifra": cifra_query,
            "keywords": kw_list,
            "label": label,
            "candidates_found": len(candidates),
            "already_in_trace": already_cached,
            "newly_inspected": newly_processed,
            "errors": errors,
            "total_matches": len(matches),
            "matches": matches,
        }
