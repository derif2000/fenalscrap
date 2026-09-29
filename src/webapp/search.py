"""Motor de búsqueda inteligente para la app web de FENALCO.

Proporciona búsqueda flexible y tolerante a fallos:
- Insensible a mayúsculas y tildes/acentos (NFKD).
- Tolerante a puntuación, comillas, guiones y espacios múltiples.
- Búsqueda por palabras desordenadas o frases exactas con comillas ("...").
- Coincidencias en título, subtítulo, categoría, URL y cuerpo del texto.
- Tolerancia a números con o sin ceros a la izquierda (ej. '074' <-> '74' para Notijurídico).
- Stemming básico en español para coincidir singular/plural (ej. 'artículos' <-> 'artículo').
- Ponderación de relevancia inteligente (títulos exactos o parciales al inicio).
- Modo de relajación en 2 fases si no hay coincidencias estrictas (evita resultados vacíos).
"""

import re
import unicodedata

# Palabras vacías en español (stopwords) que no deben penalizar si se omiten
STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "o", "u", "a", "al", "en",
    "un", "una", "unos", "unas", "que", "con", "por", "para", "es", "son",
    "se", "su", "sus", "como", "mas", "más", "sobre", "entre", "sin", "desde",
    "hasta", "este", "esta", "estos", "estas", "cual", "cuales", "lo",
}


def normalize_search_text(text: str) -> str:
    """Normaliza texto: minúsculas, sin tildes/diacríticos y sin puntuación."""
    if not text:
        return ""
    # Descomposición Unicode para separar letras de tildes
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Reemplazar cualquier caracter no alfanumérico por espacio
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def stem_word(w: str) -> str:
    """Raíz léxica simple para español (singularización de sustantivos/adjetivos)."""
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


from .drive_reader import clean_spaced_name, extract_drive_id, drive_reader


class FenalcoSearchEngine:
    """Índice en memoria para búsquedas instantáneas y altamente relevantes."""

    def __init__(self, records: list):
        cached_texts = drive_reader.get_all_cached_texts()
        self.index = []
        for r in records:

            url = r.get("url", "") or ""
            raw_title = r.get("title", "") or ""
            raw_sub = r.get("subtitle", "") or ""
            raw_cat = r.get("category", "") or ""
            # Limitado a 3.000 chars (era 15.000): reduce txt_words sets de ~120MB a ~20MB
            raw_txt = (r.get("content_text", "") or "")[:3000]

            nt = normalize_search_text(raw_title)
            ns = normalize_search_text(raw_sub)
            nc = normalize_search_text(raw_cat)
            nu = normalize_search_text(url)
            ntxt = normalize_search_text(raw_txt)

            t_tokens = nt.split()
            title_words = set(t_tokens)
            title_stems = {stem_word(w) for w in t_tokens}

            # Manejar variantes de números con y sin ceros (ej. 074, 74)
            title_numbers = set()
            for w in t_tokens:
                if w.isdigit():
                    title_numbers.add(w)
                    title_numbers.add(w.lstrip("0") or "0")
                    title_numbers.add(w.zfill(3))

            s_tokens = ns.split()
            sub_words = set(s_tokens)
            sub_stems = {stem_word(w) for w in s_tokens}

            c_tokens = nc.split()
            cat_words = set(c_tokens)

            # txt_words y txt_stems se eliminan del índice permanente:
            # eran sets de ~3.000 palabras x 4.000 registros = ~120MB cada uno.
            # El scoring de texto de cuerpo usa búsqueda directa en ntxt (substring).

            # Nombres de documentos adjuntos / embebidos (Google Drive)
            doc_words = set()
            doc_stems = set()
            doc_titles_raw = []
            doc_ids = []
            for d in r.get("documents") or []:
                raw_dname = d.get("filename") or ""
                cname = clean_spaced_name(raw_dname)
                if cname and cname.lower() not in ("view", "documento embebido", "documento adjunto"):
                    doc_titles_raw.append(cname)
                    ndoc = normalize_search_text(cname)
                    for dw in ndoc.split():
                        doc_words.add(dw)
                        doc_stems.add(stem_word(dw))
                did = extract_drive_id(d.get("url", ""))
                if did:
                    doc_ids.append(did)

            # Texto en caché de documentos asociados (limitado a 3.000 chars, era 8.000)
            cached_doc_words = set()
            cached_doc_stems = set()
            for did in doc_ids:
                cd_text = cached_texts.get(did)
                if cd_text:
                    ncdt = normalize_search_text(cd_text[:3000])
                    for cdw in ncdt.split():
                        cached_doc_words.add(cdw)
                        cached_doc_stems.add(stem_word(cdw))


            self.index.append({
                "url": url,
                "title": raw_title,
                "nt": f" {nt} ",
                "ns": f" {ns} ",
                "nc": f" {nc} ",
                "nu": nu,
                "ntxt": ntxt,  # solo para búsqueda de substring; no se guardan sets
                "title_words": title_words,
                "title_stems": title_stems,
                "title_numbers": title_numbers,
                "sub_words": sub_words,
                "sub_stems": sub_stems,
                "cat_words": cat_words,
                "doc_words": doc_words,
                "doc_stems": doc_stems,
                "doc_ids": doc_ids,
                "cached_doc_words": cached_doc_words,
                "cached_doc_stems": cached_doc_stems,
                "date": r.get("publish_date", "") or "",
            })

    def search_scores(self, query: str) -> dict:
        """Devuelve un diccionario {url: score} ordenado por relevancia."""
        raw_q = query.strip()
        if not raw_q:
            return {}

        nq = normalize_search_text(raw_q)
        if not nq:
            return {}

        # Frases exactas entre comillas (ej. "reforma tributaria")
        quoted_phrases = [
            normalize_search_text(p)
            for p in re.findall(r'"([^"]+)"', raw_q)
        ]
        quoted_phrases = [p for p in quoted_phrases if p]

        tokens = nq.split()
        if not tokens:
            return {}

        content_tokens = [t for t in tokens if t not in STOPWORDS]
        if not content_tokens:
            content_tokens = tokens

        padded_nq = f" {nq} "

        def _score_items(min_coverage_ratio: float, allow_partial: bool = False):
            results = []
            for item in self.index:
                score = 0.0

                # 1. Filtro estricto si hay comillas
                if quoted_phrases:
                    match_all_quotes = True
                    for qp in quoted_phrases:
                        pq = f" {qp} "
                        if (pq not in item["nt"] and pq not in item["ns"]
                                and qp not in item["ntxt"] and pq not in item["nc"]):
                            match_all_quotes = False
                            break
                    if not match_all_quotes:
                        continue

                # 2. Coincidencia de frase continua completa (alta prioridad)
                if padded_nq in item["nt"] or nq == item["nt"].strip():
                    score += 350.0
                    if item["nt"].strip().startswith(nq):
                        score += 100.0
                    if item["nt"].strip() == nq:
                        score += 200.0
                elif nq in item["nt"]:
                    score += 220.0
                elif padded_nq in item["ns"] or nq in item["ns"]:
                    score += 120.0
                elif padded_nq in item["nc"] or nq in item["nc"]:
                    score += 80.0
                elif nq in item["nu"]:
                    score += 60.0
                elif nq in item["ntxt"]:
                    score += 45.0

                # 3. Coincidencia por tokens / palabras individuales
                content_hits = 0
                title_hits = 0

                for t in content_tokens:
                    st = stem_word(t)
                    is_num = t.isdigit()
                    stripped_num = t.lstrip("0") if is_num else ""
                    zfilled_num = t.zfill(3) if is_num else ""

                    # Título
                    matched_title = False
                    if t in item["title_words"]:
                        score += 45.0
                        matched_title = True
                    elif is_num and (stripped_num in item["title_numbers"]
                                     or zfilled_num in item["title_numbers"]):
                        score += 45.0
                        matched_title = True
                    elif st in item["title_stems"]:
                        score += 35.0
                        matched_title = True
                    elif f" {t}" in item["nt"] or t in item["nt"]:
                        score += 25.0
                        matched_title = True

                    if matched_title:
                        title_hits += 1
                        content_hits += 1
                        continue

                    # Subtítulo
                    if t in item["sub_words"] or st in item["sub_stems"]:
                        score += 20.0
                        content_hits += 1
                        continue

                    # Categoría
                    if t in item["cat_words"]:
                        score += 15.0
                        content_hits += 1
                        continue

                    # URL
                    if t in item["nu"]:
                        score += 12.0
                        content_hits += 1
                        continue

                    # Nombres de documentos adjuntos / embebidos (Google Drive)
                    if t in item.get("doc_words", set()) or st in item.get("doc_stems", set()):
                        score += 30.0
                        content_hits += 1
                        continue

                    # Texto de documentos adjuntos (Google Drive)
                    if t in item.get("cached_doc_words", set()) or st in item.get("cached_doc_stems", set()):
                        score += 16.0
                        content_hits += 1
                        continue

                    # Texto del cuerpo del artículo: búsqueda directa en ntxt (sin sets)
                    t_in_ntxt = f" {t} " in item["ntxt"] or t in item["ntxt"]
                    st_in_ntxt = f" {stem_word(t)} " in item["ntxt"]
                    if t_in_ntxt:
                        score += 6.0
                        content_hits += 1
                    elif st_in_ntxt:
                        score += 5.0
                        content_hits += 1
                    elif is_num and (stripped_num in item["ntxt"] or zfilled_num in item["ntxt"]):
                        score += 6.0
                        content_hits += 1


                if content_hits == 0 and score == 0:
                    continue

                coverage = content_hits / len(content_tokens)

                # Umbral de cobertura requerida
                if padded_nq in item["nt"] or nq in item["nt"] or (quoted_phrases and score > 0):
                    pass
                elif coverage < min_coverage_ratio and title_hits < 2:
                    continue

                score += coverage * 60.0
                if coverage == 1.0:
                    score += 50.0
                if title_hits == len(content_tokens):
                    score += 90.0

                results.append((score, item["date"], item["url"]))

            return results

        # Fase 1: Coincidencia estricta (100% de palabras para <=3 tokens, 65% para más)
        req_ratio = 1.0 if len(content_tokens) <= 3 else 0.65
        res = _score_items(req_ratio)

        # Fase 2: Relajación automática si la fase 1 no dio resultados
        if not res and len(content_tokens) > 1:
            relaxed_ratio = 0.45 if len(content_tokens) > 3 else 0.5
            res = _score_items(relaxed_ratio, allow_partial=True)

        res.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return {url: score for score, date, url in res}
