"""Motor de búsqueda especializado en cifras, porcentajes y estadísticas para FENALCO.

Busca de manera determinística, inmediata y sin IA en:
1. Las 4.000 publicaciones y artículos (título, subtítulo y cuerpo completo).
2. Los textos extraídos de documentos adjuntos (PDFs en output/doc_cache/).
3. Los datos numéricos de gráficas y tablas extraídas mediante visión/OCR.

Provee contexto circundante, resaltado de la cifra y enlaces directos al
artículo, documento o visualizador de la gráfica.
"""

import html
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .drive_reader import IMAGE_MARKER_RE, _CACHE_DIR, extract_drive_id

# Patrón para detectar porcentajes numéricos
_PCT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por\s*ciento\b)", re.IGNORECASE)

# Patrón para cifras monetarias
_CURRENCY_RE = re.compile(r"(?:\$|cop|pesos?)\s*(\d[\d.,]*)|\b(\d[\d.,]*)\s*(?:pesos?|millones?|billones?)\b", re.IGNORECASE)


def parse_cifra_query(query: str) -> Tuple[List[re.Pattern], List[str], str]:
    """Analiza la consulta del usuario y genera patrones regex optimizados.

    Retorna:
        - patterns: lista de patrones compilados para buscar la cifra numérica.
        - keywords: palabras temáticas secundarias (ej: si busca 'ventas 26%').
        - display_label: descripción amigable de la búsqueda realizada.
    """
    q = query.strip()
    if not q:
        return [], [], ""

    pct_match = _PCT_RE.search(q)
    patterns = []
    keywords = []

    if pct_match:
        val_str = pct_match.group(1)
        # Normalizar formatos con punto y coma: ej. "1.4" o "1,4"
        clean_num = val_str.replace(",", ".")
        comma_num = val_str.replace(".", ",")
        nums_to_match = list(dict.fromkeys([val_str, clean_num, comma_num]))

        for num in nums_to_match:
            esc = re.escape(num)
            # Coincidencia estricta de porcentaje:
            # - (?<![\w.,]) : no precedido inmediatamente por letra, dígito, punto o coma (evita 0.26%, 126%, etc.)
            # - (?<![\d.,]\s) : no precedido por punto/coma con espacio (evita 0. 26%, 0, 26%)
            # - esc : el número exacto
            # - (?![.,]\d) : no seguido por punto/coma y dígito (evita 26.3%, 26,4%)
            # - \s*(?:%|por\s*ciento\b) : porcentaje o texto "por ciento"
            patterns.append(re.compile(
                rf"(?<![\w.,])(?<![\d.,]\s){esc}(?![.,]\d)\s*(?:%|por\s*ciento\b)",
                re.IGNORECASE
            ))

        # Resto de palabras secundarias
        remaining = _PCT_RE.sub(" ", q)
        words = [w.strip().lower() for w in re.findall(r"[a-záéíóúñA-ZÁÉÍÓÚÑ0-9]+", remaining) if len(w) >= 3]
        keywords = words
        display_label = f"Porcentaje «{val_str}%»"
        if keywords:
            display_label += f" con términos «{' '.join(keywords)}»"
    else:
        # Búsqueda numérica general o por frase
        # Si tiene dígitos:
        digits = re.findall(r"\b\d+(?:[.,]\d+)?\b", q)
        if digits:
            for num in digits:
                clean_num = num.replace(",", ".")
                comma_num = num.replace(".", ",")
                for n in set([num, clean_num, comma_num]):
                    esc = re.escape(n)
                    # Cifra exacta estricta sin prefijos decimales ni sub-decimales
                    patterns.append(re.compile(
                        rf"(?<![\w.,])(?<![\d.,]\s){esc}(?![.,]\d)(?!\w)",
                        re.IGNORECASE
                    ))
            
            # Palabras adicionales
            words = [w.strip().lower() for w in re.findall(r"[a-záéíóúñA-ZÁÉÍÓÚÑ]+", q) if len(w) >= 3]
            keywords = words
            display_label = f"Cifra «{' / '.join(digits)}»"
            if keywords:
                display_label += f" con términos «{' '.join(keywords)}»"
        else:
            # Búsqueda literal de texto
            esc = re.escape(q)
            patterns.append(re.compile(rf"\b{esc}\b", re.IGNORECASE))
            display_label = f"Término «{q}»"

    return patterns, keywords, display_label


def _extract_snippet(text: str, match_obj, pad: int = 140) -> str:
    """Extrae un fragmento de texto alrededor de la coincidencia y la envuelve en <mark>."""
    if not match_obj or not text:
        return ""
    start_pos = match_obj.start()
    end_pos = match_obj.end()

    # Intentar recortar en fronteras de palabras/frases
    left = max(0, start_pos - pad)
    right = min(len(text), end_pos + pad)

    prefix = "… " if left > 0 else ""
    suffix = " …" if right < len(text) else ""

    pre_text = text[left:start_pos].replace("\n", " ").strip()
    match_text = text[start_pos:end_pos].strip()
    post_text = text[end_pos:right].replace("\n", " ").strip()

    # Sanitizar HTML para prevenir inyecciones
    pre_esc = html.escape(pre_text)
    match_esc = html.escape(match_text)
    post_esc = html.escape(post_text)

    return f'{prefix}{pre_esc} <mark class="cifra-mark fw-bold text-dark px-1 rounded">{match_esc}</mark> {post_esc}{suffix}'


import unicodedata

def _norm(text: str) -> str:
    """Normaliza texto eliminando acentos y convirtiendo a minúsculas."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower().strip()


def search_cifras(
    store,
    query: str,
    keywords_filter: Optional[List[str]] = None,
    origin_filter: str = "all",
    max_results: int = 200,
) -> Dict[str, Any]:
    """Ejecuta una búsqueda exhaustiva de cifras sobre publicaciones, PDFs y gráficas.

    Args:
        store: Instancia de FenalcoData.
        query: Consulta del usuario (ej. '26%', '1.4%', '550').
        keywords_filter: Lista opcional de palabras clave para acotar la búsqueda.
        origin_filter: 'all', 'articulos', 'documentos', 'graficas'.
        max_results: Límite de resultados a retornar.

    Returns:
        Diccionario con estadísticas y lista de coincidencias estructuradas.
    """
    patterns, query_kws, label = parse_cifra_query(query)
    if not patterns:
        return {
            "query": query,
            "label": label,
            "total_matches": 0,
            "count_articulos": 0,
            "count_documentos": 0,
            "count_graficas": 0,
            "results": [],
            "docs_cached_count": 0,
            "docs_total_count": 0,
        }

    # Combinar palabras clave de la consulta con el filtro explícito
    combined_kws = list(dict.fromkeys(
        [k.strip() for k in (keywords_filter or []) if k.strip()] +
        [k.strip() for k in (query_kws or []) if k.strip()]
    ))
    norm_kws = [_norm(k) for k in combined_kws if len(_norm(k)) >= 2]
    if combined_kws:
        label += f" · Filtro: «{', '.join(combined_kws)}»"

    # Mapa rápido de doc_id -> list of parent records
    doc_to_records = {}
    for r in store.records:
        for doc in r.get("documents") or []:
            u = doc.get("url") or ""
            did = extract_drive_id(u)
            if did:
                doc_to_records.setdefault(did, []).append(r)

    results = []
    articulos_count = 0
    documentos_count = 0
    graficas_count = 0

    # 1. Búsqueda en Artículos y Publicaciones (los 4.000 registros)
    if origin_filter in ("all", "articulos"):
        for r in store.records:
            title = r.get("title") or ""
            subtitle = r.get("subtitle") or ""
            body = r.get("content_text") or ""
            full_text = f"{title}\n{subtitle}\n{body}"

            # Si hay keywords adicionales, verificar que existan en el artículo
            if norm_kws:
                art_searchable = _norm(f"{title} {subtitle} {r.get('category', '')} {body}")
                if not any(kw in art_searchable for kw in norm_kws):
                    continue

            match_found = None
            for pat in patterns:
                m = pat.search(full_text)
                if m:
                    match_found = m
                    break

            if match_found:
                articulos_count += 1
                snippet = _extract_snippet(full_text, match_found)
                results.append({
                    "id": f"art-{r.get('url')}",
                    "origin": "articulo",
                    "origin_label": "Artículo / Noticia",
                    "badge_color": "primary",
                    "icon": "newspaper",
                    "title": title or "Publicación FENALCO",
                    "subtitle": subtitle,
                    "date": r.get("publish_date") or "",
                    "category": r.get("category") or "General",
                    "kind": r.get("kind") or "blog-post",
                    "url": r.get("url") or "",
                    "snippet": snippet,
                    "documents": r.get("documents") or [],
                    "image": None,
                })

    # 2. Búsqueda en Documentos Adjuntos y Gráficas (output/doc_cache/*.txt y output/cifras_trace.json)
    cached_docs = list(Path(_CACHE_DIR).glob("*.txt")) if _CACHE_DIR.exists() else []
    
    # Cargar rastros ligeros guardados por el crawler inteligente
    trace_file = Path(__file__).resolve().parents[2] / "output" / "cifras_trace.json"
    trace_data = {}
    if trace_file.exists():
        try:
            import json as _json
            trace_data = _json.loads(trace_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    processed_dids = set()
    docs_to_search = []
    for doc_file in cached_docs:
        did = doc_file.stem
        processed_dids.add(did)
        try:
            ctxt = doc_file.read_text(encoding="utf-8", errors="ignore")
            if ctxt:
                docs_to_search.append((did, ctxt, f"Extraído de: {doc_file.name}"))
        except Exception:
            continue

    # Agregar los documentos del rastro ligero que no estén en doc_cache
    for did, t_info in trace_data.items():
        if did not in processed_dids:
            processed_dids.add(did)
            t_txt = t_info.get("full_text_compact", "")
            if t_txt:
                fn = t_info.get("filename") or "Documento"
                docs_to_search.append((did, t_txt, f"Rastro ligero de: {fn}"))

    docs_cached_count = len(processed_dids)
    total_docs_in_db = sum(len(r.get("documents") or []) for r in store.records)

    for did, ctxt, subtitle_meta in docs_to_search:
        parents = doc_to_records.get(did, [])
        p_rec = parents[0] if parents else {}

        # Si hay palabras clave, deben coincidir en el título del artículo, nombre del PDF o texto del documento
        if norm_kws:
            parent_meta = f"{p_rec.get('title','')} {p_rec.get('subtitle','')} {p_rec.get('category','')} {subtitle_meta}"
            searchable_doc = _norm(f"{parent_meta} {ctxt}")
            if not any(kw in searchable_doc for kw in norm_kws):
                continue

        ocr_sep = "--- [DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF] ---"
        has_ocr = ocr_sep in ctxt
        ocr_pos = ctxt.find(ocr_sep) if has_ocr else len(ctxt)

        match_found = None
        for pat in patterns:
            m = pat.search(ctxt)
            if m:
                match_found = m
                break

        if match_found:
            m_pos = match_found.start()
            is_in_ocr = has_ocr and m_pos > ocr_pos
            origin_type = "grafica" if is_in_ocr else "documento"

            if origin_filter != "all":
                if origin_filter == "documentos" and origin_type != "documento":
                    continue
                if origin_filter == "graficas" and origin_type != "grafica":
                    continue

            if origin_type == "grafica":
                graficas_count += 1
            else:
                documentos_count += 1

            snippet = _extract_snippet(ctxt, match_found)

            # Buscar parent record(s)
            parents = doc_to_records.get(did, [])
            p_rec = parents[0] if parents else {}
            title = p_rec.get("title") or f"Documento adjunto [{did[:12]}…]"
            p_date = p_rec.get("publish_date") or ""
            p_cat = p_rec.get("category") or "Documento Técnico"
            p_url = p_rec.get("url") or ""

            # Extraer imagen asociada si es gráfica
            img_data = None
            if is_in_ocr:
                # Buscar marcas [[IMG:src|caption]] en la sección OCR
                img_matches = list(IMAGE_MARKER_RE.finditer(ctxt))
                if img_matches:
                    # Encontrar la marca de imagen más cercana a la coincidencia
                    closest_img = min(img_matches, key=lambda im: abs(im.start() - m_pos))
                    img_data = {
                        "src": closest_img.group("src"),
                        "caption": closest_img.group("caption") or "Gráfica / Tabla extraída",
                    }

            results.append({
                "id": f"doc-{did}-{origin_type}",
                "doc_id": did,
                "origin": origin_type,
                "origin_label": "Gráfica / Tabla (OCR)" if origin_type == "grafica" else "Documento PDF",
                "badge_color": "warning" if origin_type == "grafica" else "info",
                "icon": "bar-chart-fill" if origin_type == "grafica" else "file-earmark-pdf-fill",
                "title": title,
                "subtitle": subtitle_meta,
                "date": p_date,
                "category": p_cat,
                "kind": "document",
                "url": p_url,
                "drive_url": f"https://drive.google.com/file/d/{did}/view",
                "snippet": snippet,
                "documents": p_rec.get("documents") or [],
                "image": img_data,
            })

    # Ordenar por fecha más reciente
    results.sort(key=lambda x: str(x.get("date") or ""), reverse=True)

    # Si la lista es más amplia que max_results, acotar
    capped_results = results[:max_results]

    return {
        "query": query,
        "label": label,
        "total_matches": len(results),
        "count_articulos": articulos_count,
        "count_documentos": documentos_count,
        "count_graficas": graficas_count,
        "results": capped_results,
        "docs_cached_count": docs_cached_count,
        "docs_total_count": total_docs_in_db,
    }
