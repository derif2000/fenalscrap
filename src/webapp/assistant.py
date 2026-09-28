"""Asistente de IA para consultar los datos de FENALCO.

Combina una búsqueda semántica local (RAG) sobre los registros extraídos con
un modelo de lenguaje gratuito (Google Gemini) para responder en lenguaje
natural citando las fuentes de la base de datos.

La clave de Gemini se lee de la variable de entorno GEMINI_API_KEY o del
archivo .env. Si no hay clave, el asistente responde con la búsqueda local
(los resultados más relevantes), de modo que siempre funciona.
"""

import os
import re
import unicodedata
from pathlib import Path

from .data import FenalcoData


def _load_env():
    env = Path(__file__).resolve().parents[2] / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")


_load_env()

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", "120"))

# Lista de modelos en orden de preferencia con fallback automático si hay 503 o cuota agotada
_cand_models = [
    GEMINI_MODEL,
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]
_seen_m = set()
GEMINI_MODEL_FALLBACKS = [m for m in _cand_models if m and not (m in _seen_m or _seen_m.add(m))]
GEMINI_MODEL_LABEL = f"Gemini ({GEMINI_MODEL})"
GROQ_MODEL_LABEL = ""

AI_PROVIDER = "gemini" if GEMINI_KEY else ""

# Palabras vacías gramaticales y de relleno conversacional
_STOPWORDS = {
    "el", "la", "los", "las", "de", "del", "y", "o", "u", "a", "al", "en",
    "un", "una", "unos", "unas", "que", "con", "por", "para", "es", "son",
    "se", "su", "sus", "como", "mas", "más", "cual", "cuales", "cuál",
    "cuáles", "sobre", "aquí", "ahi", "hay", "tiene", "tienen",
    "hacer", "haz", "quiero", "necesito", "saber", "ver", "listar", "lista",
    "cuanto", "cuánto", "cuando", "cuándo", "cada",
}


def _norm_token(text: str) -> str:
    """Normaliza texto: minúsculas y sin acentos para comparar robustamente."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def _stem(w: str) -> str:
    """Raíz léxica simple para español (singularización de sustantivos/adjetivos)."""
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


def _tokenize(text: str) -> list:
    text = _norm_token(text)
    tokens = re.findall(r"[a-z0-9]+", text)
    filtered = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    return filtered if filtered else [t for t in tokens if len(t) > 1]


# Palabras/señales que indican que la consulta pide DATOS CUANTITATIVOS que
# probablemente estén en gráficos, tablas o imágenes dentro de PDFs (y por tanto
# requieren visión/OCR). Las palabras van SIN acentos porque _norm_token las
# normaliza (p. ej. "gráfico" -> "grafico", "imágenes" -> "imagenes").
_DATA_SIGNAL_WORDS = [
    "cifra", "cifras", "tasa", "tasas", "porcentaje",
    "porcentajes", "%", "estadistica", "estadisticas", "indicador", "indicadores",
    "grafico", "graficos", "grafica", "graficas", "grafo", "grafos", "diagrama",
    "diagramas", "imagen", "imagenes", "tabla", "tablas", "comparar",
    "comparacion", "compare", "ranking", "promedio",
    "cantidad", "cantidades", "valor", "valores", "numero", "numeros", "total",
    "totales", "cuanto", "cuantos", "cuanta", "cuantas", "monto", "montos",
    "variacion", "varia", "evolucion", "tendencia",
    # Términos que casi siempre piden datos de una comparación/gráfica de series
    "balance", "balence", "ventas", "dane", "emc", "encuesta", "vs",
    "serie", "series", "comparativo", "barras", "columnas", "linea", "lineas",
    "datos", "dato", "margen", "ingresos", "utilidad",
]

_FOLLOWUP_FILLERS_OCR_TRIGGER = {"grafica", "grafico", "graficas", "graficos",
                                 "tabla", "tablas", "imagen", "imagenes",
                                 "datos", "dato", "balance", "balence"}

_PCT_SEARCH_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*(?:%|por\s*ciento\b)", re.IGNORECASE)
_META_INSTRUCTION_RE = re.compile(
    r"\b(mira|mire|miren|busca|busque|buscame|revisa|revise|documento|documentos|"
    r"post|posts|articulo|articulos|publicacion|publicaciones|informe|informes|"
    r"noticia|noticias|incluyendo|incluye|imagen|imagenes|grafica|graficas|"
    r"grafico|graficos|tabla|tablas|demas|dime|dame|cuenta|cuales|en cuales|"
    r"existe|existen|aparece|aparecen|como dato|como cifra|dato|datos|valor|valores|"
    r"todo|todos|toda|todas|disponible|disponibles)\b",
    re.IGNORECASE
)


def _needs_ocr(question: str) -> bool:
    """Determina si una consulta requiere OCR/visión sobre las imágenes de los PDFs.

    El OCR (llamada a la API de visión) es costoso y lento, por eso solo se activa
    cuando la pregunta busca DATOS NUMÉRICOS/ESTRUCTURADOS que suelen estar en
    gráficos, tablas o imágenes incrustadas. Para búsquedas de texto normales
    ("bitácoras del año 2026") no hace falta: basta el texto digital.
    """
    if not question:
        return False
    q = _norm_token(question)
    if any(w in q for w in _DATA_SIGNAL_WORDS):
        return True
    # Si menciona "gráfica"/"tabla"/"imagen/…datos" aunque sea con relleno,
    # (p. ej. "los datos de la gráfica") se fuerza OCR.
    tokens = set(_tokenize(question))
    if tokens & _FOLLOWUP_FILLERS_OCR_TRIGGER:
        return True
    # Patrones "por ciudad / por departamento / por región / por municipio"...
    if re.search(
        r"\bpor\s+(ciudad|ciudades|departamento|departamentos|region|regiones|"
        r"municipio|municipios|pais|paises|provincia|provincias)\b", q):
        return True
    return False


# Términos conversacionales o referenciales que NO aportan tema por sí solos
# (sin acentos, porque _norm_token los normaliza). Si una pregunta está compuesta
# sobre todo por estos, hay que heredar el tema de la última pregunta real.
_FOLLOWUP_FILLERS = {
    "dame", "dime", "damelos", "damela", "damelo", "da", "muestra", "muestrame",
    "listame", "listame", "lista", "datos", "dato", "grafica", "grafico",
    "graficos", "graficas", "tabla", "tablas", "imagen", "imagenes", "si",
    "dale", "ok", "vale", "eso", "esos", "esa", "esas", "esto", "estos",
    "esta", "estas", "este", "ver", "quiero", "necesito", "saber", "cuenta",
    "cual", "cuales", "explique", "explica", "explicalo", "detalle", "detalla",
    "informa", "informacion", "sobre", "respecto", "mencionado", "mencionada",
    "anterior", "arriba",
}


_REPLICA_CORRECTION_PATTERNS = [
    r"\bte ped[ií]\b",
    r"\bno dice eso\b",
    r"\blo est[aá]s inventando\b",
    r"\blo estas inventando\b",
    r"\bte lo inventaste\b",
    r"\best[aá]s inventando\b",
    r"\bestas inventando\b",
    r"\binventando\b",
    r"\bmentira\b",
    r"\bno es cierto\b",
    r"\bbusca bien\b",
    r"\bdebe (de )?estar ah[ií]\b",
    r"\bque no+\b",
    r"\bno pero\b",
    r"\bsi pero\b",
    r"\bpero no veo\b",
    r"\bno veo los que\b",
    r"\btexto exacto\b",
    r"\bcita literal\b",
    r"\bliteralmente\b",
    r"\btranscribe\b",
    r"\btranscripci[oó]n\b",
    r"\bcu[aá]ntas p[aá]ginas\b",
    r"\bcuantas paginas\b",
    r"\ben ese mismo\b",
    r"\ben ese documento\b",
    r"\bel documento anterior\b",
    r"\bde ese documento\b",
    r"\bde este documento\b",
    r"\bdel documento\b",
    r"\bde la gr[aá]fica\b",
    r"\bdel gr[aá]fico\b",
    r"\bde la tabla\b",
    r"\bde las conclusiones\b",
    r"\bde la conclusi[oó]n\b",
    r"\bpara cada estrato\b",
    r"\bde eso\b",
    r"\bde estos\b",
    r"\bde esas\b",
]


def _is_replica_or_correction(question: str) -> bool:
    """True si el usuario está haciendo una réplica, reclamo, corrección o pidiendo exactitud sobre lo previo."""
    if not question:
        return False
    q = _norm_token(question)
    for pat in _REPLICA_CORRECTION_PATTERNS:
        if re.search(pat, q):
            return True
    return False


def _is_substantive(question: str) -> bool:
    """True si la pregunta trae un tema concreto independiente.

    Se considera sustantiva si menciona un año/fecha (19xx-20xx) o si tiene al
    menos 2 términos que no sean de relleno conversacional y NO sea una réplica.
    """
    if not question:
        return False
    if _is_replica_or_correction(question):
        return False
    q = _norm_token(question)
    if re.search(r"\b(19|20)\d{2}\b", q):
        return True
    meaningful = [t for t in _tokenize(question) if t not in _FOLLOWUP_FILLERS]
    return len(meaningful) >= 2


_FOLLOWUP_CALC_WORDS = {
    "promedia", "promediar", "promedio", "promedios", "calcula", "calcular",
    "calculame", "calculo", "calculos", "suma", "sumar", "sumame", "totaliza",
    "totalizar", "total", "diferencia", "resta", "restar", "compara", "comparar",
    "mayor", "menor", "pico", "minimo", "maximo", "tendencia",
}


def _is_followup(question: str) -> bool:
    """True si la consulta es de seguimiento, cálculo, comparación o referencia sobre lo anterior."""
    if not question:
        return False
    if _is_replica_or_correction(question):
        return True
    q = _norm_token(question)
    tokens = set(_tokenize(question))
    if tokens & _FOLLOWUP_CALC_WORDS:
        return True
    followup_markers = [
        "de arriba", "aqui arriba", "estos mismos", "estas mismas", "esos mismos",
        "de la tabla", "de la grafica", "del grafico", "del cuadro", "de los datos",
        "de las cifras", "cual fue el", "cual es el", "que mes", "en que mes",
        "si pero", "ok pero", "pero necesito", "y en", "y para", "y de", "y respecto a",
        "de ellos", "de ellas", "de estos", "de estas", "de esos", "de esas",
        "en ese", "en esa", "en este", "en esta", "del estudio", "del informe",
        "la conclusion", "las conclusiones", "la grafica", "el grafico",
        "para cada", "por cada", "los datos exactos", "datos exactos",
        "el documento anterior", "en ese documento", "en ese mismo",
    ]
    if any(marker in q for marker in followup_markers):
        return True
    return not _is_substantive(question)




class Assistant:
    """Asistente que busca en los datos y responde en lenguaje natural."""

    def _init_gemini(self):
        """Inicializa o recarga el cliente Gemini leyendo la configuración actual de .env."""
        _load_env()
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        model = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite").strip()
        timeout = float(os.environ.get("GEMINI_TIMEOUT", "120"))

        self.key = key
        self.provider = "gemini" if key else ""
        self._gemini = None
        self._gemini_model = model
        self._init_error = None

        if key:
            try:
                from google.genai import Client, types as genai_types
                self._gemini = Client(
                    api_key=key,
                    http_options=genai_types.HttpOptions(timeout=int(timeout * 1000)),
                )
            except Exception as exc:
                self._init_error = str(exc)
        else:
            self._init_error = "No hay GEMINI_API_KEY configurada"

    def __init__(self, data: FenalcoData):
        self.data = data
        self._init_gemini()

    @property
    def has_ai(self) -> bool:
        return self._gemini is not None

    def ai_status(self) -> dict:
        """Verifica el estado real de la IA haciendo una llamada mínima a la API.

        Envía un prompt de una sola palabra a Gemini para confirmar que la API
        responde correctamente (clave válida, cuota disponible, red accesible).

        Returns:
            dict con claves:
              - ok (bool): True si la API respondió correctamente
              - provider (str): nombre del proveedor
              - model (str): modelo configurado
              - label (str): texto breve para la UI
              - detail (str): detalle ampliado (incluye error si hay)
              - latency_ms (int|None): latencia del ping en milisegundos
        """
        self._init_gemini()
        import time as _time

        model = self._gemini_model or os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

        # Sin clave configurada — no hay nada que probar
        if not self.key:
            return {
                "ok": False,
                "provider": "",
                "model": "",
                "label": "IA no configurada",
                "detail": "No se encontró GEMINI_API_KEY en .env. "
                          "El asistente funciona en modo búsqueda local.",
                "latency_ms": None,
            }

        # Cliente no se pudo inicializar
        if self._gemini is None:
            return {
                "ok": False,
                "provider": "Gemini",
                "model": model,
                "label": "IA no disponible · Error al iniciar cliente",
                "detail": f"Falló la creación del cliente Gemini: {self._init_error}",
                "latency_ms": None,
            }

        # ---- Ping real: llamada mínima a la API ----
        t0 = _time.monotonic()
        try:
            resp = self._gemini.models.generate_content(
                model=model,
                contents="Di solo la palabra: OK",
                config={"max_output_tokens": 5},
            )
            latency_ms = int((_time.monotonic() - t0) * 1000)
            # Verificar que la respuesta tiene texto (no bloqueada)
            reply = ""
            try:
                reply = resp.text.strip()
            except Exception:
                pass
            if reply:
                return {
                    "ok": True,
                    "provider": "Gemini",
                    "model": model,
                    "label": f"IA operativa · {model}",
                    "detail": f"Ping exitoso en {latency_ms} ms · Proveedor: Google Gemini · Modelo: {model}",
                    "latency_ms": latency_ms,
                }
            else:
                return {
                    "ok": False,
                    "provider": "Gemini",
                    "model": model,
                    "label": "IA bloqueada · Respuesta vacía",
                    "detail": f"La API respondió pero sin texto (posible bloqueo de contenido). Latencia: {latency_ms} ms",
                    "latency_ms": latency_ms,
                }
        except Exception as exc:
            latency_ms = int((_time.monotonic() - t0) * 1000)
            err_str = str(exc)
            # Clasificar el error para mensajes más claros
            if "API_KEY" in err_str.upper() or "INVALID_ARGUMENT" in err_str.upper() or "api key" in err_str.lower():
                label = "IA · Clave de API inválida"
                detail = f"La GEMINI_API_KEY no es válida o fue revocada. Error: {err_str}"
            elif "QUOTA" in err_str.upper() or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str.upper():
                label = "IA · Cuota agotada"
                detail = f"Se agotó la cuota de la API de Gemini. Error: {err_str}"
            elif "TIMEOUT" in err_str.upper() or "timed out" in err_str.lower():
                label = "IA · Tiempo de espera agotado"
                detail = f"La API no respondió en el tiempo límite ({GEMINI_TIMEOUT}s). Error: {err_str}"
            elif "connect" in err_str.lower() or "network" in err_str.lower() or "connection" in err_str.lower():
                label = "IA · Sin conexión a internet"
                detail = f"No se pudo conectar a la API de Gemini. Verifica la red. Error: {err_str}"
            else:
                label = "IA no disponible · Error de API"
                detail = f"Error al llamar a Gemini: {err_str}"
            return {
                "ok": False,
                "provider": "Gemini",
                "model": model,
                "label": label,
                "detail": detail,
                "latency_ms": latency_ms,
            }

    # ----------------------------------------------------------- búsqueda
    def search(self, query: str, top_n: int = None, fetch_docs: bool = True,
               enable_ocr: bool | None = None) -> list:
        """Busca y devuelve todas las fuentes que coincidan con la consulta.
        
        Aprovecha el motor de búsqueda avanzado FenalcoSearchEngine, coincide en títulos,
        textos, categorías y documentos adjuntos/embebidos de Google Drive, extrayendo
        el texto de los documentos para proveer contexto completo.
        
        enable_ocr: si es None se deduce de la propia consulta; si es True/False
        se fuerza/desactiva el OCR de imágenes de los PDFs.
        """
        norm_q = _norm_token(query)
        tok_q = _tokenize(query)
        if not tok_q:
            return []

        # 0. Limpieza de palabras de meta-instrucción ("mira cada documento y post...", "dime en cuáles")
        clean_q = _META_INSTRUCTION_RE.sub(" ", query).strip()
        search_query_term = clean_q if len(clean_q) >= 2 else query

        # 1. Búsqueda principal a través de FenalcoSearchEngine
        scores = {}
        if hasattr(self.data, "search_engine") and self.data.search_engine:
            scores = self.data.search_engine.search_scores(search_query_term)
            if not scores and search_query_term != query:
                scores = self.data.search_engine.search_scores(query)

        # 1b. Detección y bonificación masiva de porcentajes específicos (ej. "26%", "47.2%")
        pct_matches = _PCT_SEARCH_RE.findall(query)
        if pct_matches:
            from .drive_reader import drive_reader
            cached_texts = drive_reader.get_all_cached_texts()
            for r in self.data.records:
                u = r.get("url") or ""
                t_and_b = f"{r.get('title', '')} {r.get('subtitle', '')} {r.get('content_text', '')}"
                found_pct = False
                for p in pct_matches:
                    p_clean = p.replace(",", ".")
                    p_comma = p.replace(".", ",")
                    pct_pats = [
                        rf"(?<![\w.,])(?<![\d.,]\s){re.escape(p)}(?![.,]\d)\s*(?:%|por\s*ciento\b)",
                        rf"(?<![\w.,])(?<![\d.,]\s){re.escape(p_clean)}(?![.,]\d)\s*(?:%|por\s*ciento\b)",
                        rf"(?<![\w.,])(?<![\d.,]\s){re.escape(p_comma)}(?![.,]\d)\s*(?:%|por\s*ciento\b)",
                    ]
                    for pat in pct_pats:
                        if re.search(pat, t_and_b, re.IGNORECASE):
                            found_pct = True
                            break
                    if not found_pct:
                        for d in r.get("documents") or []:
                            from .drive_reader import extract_drive_id
                            did = extract_drive_id(d.get("url", ""))
                            if did and did in cached_texts:
                                ctxt = cached_texts[did]
                                for pat in pct_pats:
                                    if re.search(pat, ctxt, re.IGNORECASE):
                                        found_pct = True
                                        break
                            if found_pct:
                                break
                    if found_pct:
                        break

                if found_pct and u:
                    scores[u] = scores.get(u, 0.0) + 600.0

        matched_records = []
        if scores:
            for url, score in scores.items():
                rec = self.data.by_url.get(url)
                if rec:
                    matched_records.append((score, rec))
            matched_records.sort(key=lambda x: -x[0])

        # 2. Fallback de búsqueda directa si search_scores no devolvió registros
        if not matched_records:
            numbers = [t for t in tok_q if t.isdigit()]
            meaningful_words = [t for t in tok_q if not t.isdigit()]
            meaningful_stems = [_stem(t) for t in meaningful_words]

            scored = []
            for r in self.data.records:
                title = _norm_token(r.get("title") or "")
                subtitle = _norm_token(r.get("subtitle") or "")
                body = _norm_token((r.get("content_text") or "")[:4000])
                category = _norm_token(r.get("category") or "")
                all_text = f"{title} {subtitle} {category} {body}"

                score = 0.0
                hits = 0

                # Frase exacta
                if len(meaningful_words) >= 2:
                    phrase = " ".join(meaningful_words)
                    phrase_stem = " ".join(meaningful_stems)
                    title_stem = " ".join([_stem(w) for w in re.findall(r"[a-z0-9]+", title)])
                    if phrase in title or phrase_stem in title_stem:
                        score += 120.0
                        hits += 1
                    elif phrase in all_text:
                        score += 30.0
                        hits += 1

                # Números (ej. "057", "2026")
                for num in numbers:
                    num_int = int(num)
                    pattern = rf"\b0*{num_int}\b"
                    if re.search(pattern, title):
                        score += 90.0
                        hits += 1
                    elif re.search(pattern, all_text):
                        score += 15.0
                        hits += 1

                # Palabras individuales
                for t, stem in zip(meaningful_words, meaningful_stems):
                    if t in title or stem in title:
                        score += 25.0
                        hits += 1
                    elif t in subtitle or stem in subtitle:
                        score += 12.0
                        hits += 1
                    elif t in category or stem in category:
                        score += 10.0
                        hits += 1

                    cnt = body.count(stem)
                    if cnt > 0:
                        score += min(cnt, 3) * 1.5
                        hits += 1

                if meaningful_stems and all(s in title for s in meaningful_stems):
                    score += 40.0

                if hits:
                    pdate = r.get("publish_date") or ""
                    if pdate:
                        try:
                            yr = int(pdate[:4])
                            score += (yr - 2020) * 2.0
                        except Exception:
                            pass
                    scored.append((score, r))

            scored.sort(key=lambda x: -x[0])
            matched_records = scored

        # Si top_n es numérico se corta; si es None, se devuelven TODAS las fuentes que coincidan (con tope de seguridad de 100)
        if top_n is not None and top_n > 0:
            results_records = [r for _, r in matched_records[:top_n]]
        else:
            results_records = [r for _, r in matched_records[:100]]

        # Extraer texto de documentos adjuntos de Google Drive
        from .drive_reader import drive_reader, clean_spaced_name

        # El OCR/visión solo se usa cuando la consulta pide datos que probablemente
        # estén en gráficos/tablas/imágenes de los PDFs (no en búsquedas de texto).
        needs_ocr = _needs_ocr(query) if enable_ocr is None else bool(enable_ocr)

        out = []
        for idx, r in enumerate(results_records):
            text = r.get("content_text") or ""
            raw_docs = r.get("documents") or []

            cleaned_docs = []
            for d in raw_docs:
                raw_fn = d.get("filename") or ""
                cfn = clean_spaced_name(raw_fn) or "Documento adjunto"
                cleaned_docs.append({"filename": cfn, "url": d.get("url", "")})

            doc_texts = []
            if fetch_docs and raw_docs:
                from .drive_reader import extract_drive_id
                if idx < 4:
                    fetch_timeout = min(GEMINI_TIMEOUT, 30.0)
            doc_texts = []
            if fetch_docs and raw_docs:
                from .drive_reader import extract_drive_id
                # Priorizar extracción de documentos en la fuente principal (top 1-2)
                # para no ralentizar la consulta descargando PDFs innecesarios.
                if idx < 2:
                    fetch_timeout = min(GEMINI_TIMEOUT, 30.0)
                    doc_texts = drive_reader.get_record_documents_text(
                        r, max_docs=1, timeout=fetch_timeout, skip_privacy=True,
                        enable_ocr=needs_ocr,
                    )
                else:
                    for d in raw_docs[:1]:
                        u = d.get("url") or ""
                        did = extract_drive_id(u)
                        if did and drive_reader.is_cached(did):
                            ctxt = drive_reader.get_cached_text(did)
                            if ctxt:
                                from .drive_reader import IMAGE_MARKER_RE
                                doc_texts.append({
                                    "url": u,
                                    "filename": clean_spaced_name(d.get("filename", "")),
                                    "doc_id": did,
                                    "text": IMAGE_MARKER_RE.sub("", ctxt),
                                })

            # Filtrar imágenes: solo incluir aquellas que sean relevantes a la consulta
            # para no saturar la vista con fotos o gráficos no solicitados.
            all_imgs = [img for dt in doc_texts for img in (dt.get("images") or [])]
            relevant_imgs = []
            if all_imgs:
                q_words = [t for t in tok_q if len(t) > 2 and not t.isdigit()]
                scored_imgs = []
                for im in all_imgs:
                    cap = _norm_token(im.get("caption") or "")
                    src = _norm_token(im.get("src") or "")
                    score = sum(15 for w in q_words if w in cap)
                    score += sum(5 for w in q_words if w in src)
                    for phrase_len in (3, 2):
                        for p_idx in range(len(q_words) - phrase_len + 1):
                            subphrase = " ".join(q_words[p_idx:p_idx + phrase_len])
                            if subphrase in cap:
                                score += 35
                    if score > 0:
                        scored_imgs.append((score, im))

                if scored_imgs:
                    scored_imgs.sort(key=lambda x: -x[0])
                    relevant_imgs = [im for _, im in scored_imgs[:1]]
                elif any(w in norm_q for w in ["grafica", "imagen", "tabla", "diagrama", "grafico"]):
                    if idx == 0:
                        relevant_imgs = all_imgs[:1]

            out.append({
                "title": r.get("title") or "",
                "url": r.get("url") or "",
                "category": r.get("category") or "",
                "kind": r.get("kind") or "",
                "publish_date": r.get("publish_date") or "",
                "subtitle": r.get("subtitle") or "",
                "excerpt": text[:1200].strip(),
                "documents": cleaned_docs,
                "doc_texts": doc_texts,
                "images": relevant_imgs[:2],
                "has_docs": len(cleaned_docs) > 0,
                "docs_read": len(doc_texts),
            })
        return out

    # --------------------------------------------------------------- RAG
    def _build_prompt(self, question: str, results: list, history: list = None) -> str:
        ctx_lines = []
        char_budget = 70000
        current_chars = 0

        for i, r in enumerate(results, 1):
            fecha = f" ({r['publish_date']})" if r.get("publish_date") else ""
            cat = r.get("category") or "General"
            block = [
                f"[{i}] REGISTRO / ARTÍCULO WEB: «{r['title']}»{fecha} — Categoría: {cat}",
                f"    URL: {r['url']}",
            ]
            if r.get("subtitle"):
                block.append(f"    Subtítulo: {r['subtitle']}")
            if r.get("excerpt"):
                block.append(f"    [ORIGEN: CONTENIDO DEL REGISTRO / ARTÍCULO WEB]:\n    {r['excerpt']}")

            # Incorporar texto extraído de documentos de Google Drive
            doc_texts = r.get("doc_texts") or []
            if doc_texts:
                block.append("    --- DOCUMENTOS ADJUNTOS / EMBEBIDOS (Google Drive) ---")
                for dt in doc_texts:
                    fname = dt.get("filename") or "Documento"
                    durl = dt.get("url") or ""
                    dtext = (dt.get("text") or "").strip()
                    if dtext:
                        ocr_marker = "--- [DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF] ---"
                        if ocr_marker in dtext:
                            main_part, ocr_part = dtext.split(ocr_marker, 1)
                            max_main = 20000 if i <= 2 else (4000 if i <= 5 else 1800)
                            formatted_doc = (
                                f"[ORIGEN: DOCUMENTO PDF (TEXTO DIGITAL) — Archivo «{fname}»]:\n"
                                f"{main_part[:max_main].strip()}\n\n"
                                f"[ORIGEN: GRÁFICAS / TABLAS / IMÁGENES (OCR) DENTRO DEL PDF — Archivo «{fname}»]:\n"
                                f"{ocr_part.strip()}"
                            )
                        else:
                            max_doc_len = 25000 if i <= 2 else (5000 if i <= 5 else 1800)
                            formatted_doc = (
                                f"[ORIGEN: DOCUMENTO PDF (TEXTO DIGITAL) — Archivo «{fname}»]:\n"
                                f"{dtext[:max_doc_len]}"
                            )

                        block.append(
                            f"    • Archivo adjunto: «{fname}» ({durl})\n"
                            f"      {formatted_doc}"
                        )
                    else:
                        block.append(f"    • Archivo adjunto: «{fname}» ({durl})")
            elif r.get("documents"):
                doc_summary = ", ".join([d["filename"] for d in r["documents"][:3]])
                block.append(f"    Archivos adjuntos disponibles: {doc_summary}")

            block_str = "\n".join(block)
            if current_chars + len(block_str) > char_budget:
                ctx_lines.append(f"[{i}] {r['title']}{fecha} (URL: {r['url']})")
                current_chars += len(ctx_lines[-1])
            else:
                ctx_lines.append(block_str)
                current_chars += len(block_str)

        context = "\n\n".join(ctx_lines)

        # Incluir historial reciente de conversación con detalle suficiente para tablas y cálculos
        history_text = ""
        if history:
            recent = history[-6:]
            lines = []
            for m in recent:
                role = "Usuario" if m.get("role") == "user" else "Asistente"
                content = (m.get("content") or "").strip()
                # Permitir hasta 6000 caracteres por mensaje para no cortar tablas ni cifras
                lines.append(f"{role}:\n{content[:6000]}")
            if lines:
                history_text = "\n\nHISTORIAL DE CONVERSACIÓN RECIENTE (memoria activa del chat):\n" + "\n\n".join(lines)

        return (
            "Eres un asistente analista experto en la Federación Nacional de Comerciantes "
            "de Colombia (FENALCO). Respondes en español, de forma clara, profesional, rigurosa y fiel a las fuentes.\n\n"
            "CONTEXTO (fuentes y documentos adjuntos de FENALCO):\n"
            + (context or "No se encontraron fuentes coincidentes para esta consulta.") +
            history_text +
            "\n\nPREGUNTA DEL USUARIO:\n" + question +
            "\n\nInstrucciones fundamentales (OBLIGATORIAS):\n"
            "- ATRIBUCIÓN EXACTA Y EXPLÍCITA DEL ORIGEN DE CIFRAS (REGLA MANDATORIA):\n"
            "  Cada vez que menciones una cifra, porcentaje, cantidad o dato numérico, DEBES indicar\n"
            "  su origen EXACTO usando una línea de blockquote Markdown (comenzando con '>') así:\n"
            "  1. Si viene del REGISTRO / ARTÍCULO WEB:\n"
            "     > 📍 Origen: Registro/artículo web [N] «Título del artículo»\n"
            "  2. Si viene del TEXTO DIGITAL de un PDF adjunto:\n"
            "     > 📍 Origen: Texto digital del PDF «NombreArchivo.pdf» — pág. X [N]\n"
            "  3. Si viene de una IMAGEN, GRÁFICA o TABLA (OCR) dentro del PDF:\n"
            "     > 📍 Origen: Gráfica/Tabla (OCR) en «NombreArchivo.pdf» — pág. X [N]\n"
            "  NUNCA presents una cifra sin esa línea de origen en blockquote. Es obligatorio.\n"
            "- CONTINUIDAD DEL HILO Y DOCUMENTO ACTIVO: Mantén la coherencia con la conversación. "
            "Si el usuario pregunta sobre el documento, gráfica, conclusiones, estrato, o tema tratado "
            "en los turnos anteriores (ej. 'de eso', 'en ese documento', 'la gráfica', 'las conclusiones', 'los datos'), "
            "enfoca tu respuesta prioritariamente en la fuente activa [1]. No saltes a otros documentos desconectados.\n"
            "- FIDELIDAD ABSOLUTA Y CERO ALUCINACIÓN: Basa tus respuestas ÚNICAMENTE en los textos "
            "y datos reales del CONTEXTO. Si un dato no aparece, dilo claramente. NUNCA inventes cifras.\n"
            "- CITAS TEXTUALES: Cuando el usuario pida el texto exacto, transcribe de forma 100% LITERAL. "
            "PROHIBIDO inventar texto entre comillas.\n"
            "- DATOS DE GRÁFICAS Y TABLAS (OCR): Cuando el usuario pregunte por porcentajes o datos, "
            "revisa con especial atención la sección '[DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF]' y "
            "entrega las cifras exactas que fueron transcritas de las gráficas.\n"
            "- NÚMERO DE PÁGINAS: Usa los marcadores '--- [Página X de Y] ---' para indicar páginas con precisión.\n"
            "- ALCANCE: La base tiene >4.000 artículos y >3.700 documentos. Tu contexto son solo las fuentes "
            "más relevantes para esta consulta. Sé transparente sobre esto si te preguntan.\n"
            "- MEMORIA DE CÁLCULO: Si te piden promediar, sumar o comparar, realiza el cálculo paso a paso.\n"
            "- FORMATO DE CITAS: Cita las fuentes con [1], [2], etc. Sin generar enlaces Markdown rotos.\n"
        )

    def _get_active_source(self, history: list = None) -> tuple[str, dict | None]:
        """Obtiene el título y el objeto de la fuente activa en el turno anterior."""
        if not history:
            return "", None
        for m in reversed(history):
            if m.get("role") == "assistant" and m.get("sources"):
                srcs = m.get("sources")
                if srcs and srcs[0].get("title"):
                    return srcs[0]["title"], srcs[0]
        for m in reversed(history):
            if m.get("role") == "user":
                p = m.get("content", "")
                if p and _is_substantive(p):
                    return p.strip(), None
        return "", None

    def _resolve_query(self, question: str, history: list = None) -> str:
        """Si la pregunta es de seguimiento, réplica o referencial,
        la enriquece con el título del documento activo para no desviar la búsqueda."""
        if not history:
            return question

        is_rep = _is_replica_or_correction(question)
        is_fol = _is_followup(question)
        if not (is_rep or is_fol):
            return question

        doc_title, _ = self._get_active_source(history)
        if not doc_title:
            return question

        # Si es una réplica o reclamo (ej. "no dice eso dime la verdad lo estás inventando" o "te pedí el texto exacto"),
        # anclar la búsqueda al documento activo y extraer solo palabras clave informativas
        if is_rep:
            clean_q = re.sub(
                r"\b(no dice eso|dime la verdad|lo estas inventando|te lo inventaste|estas inventando|"
                r"te pedi el texto exacto|no un resumen|busca bien|debe de estar ahi|que no|no pero|"
                r"si veo esos datos pero no veo los que te pido de)\b",
                "", _norm_token(question)
            ).strip()
            if clean_q:
                return f"{doc_title} {clean_q}".strip()
            return doc_title

        return f"{doc_title} {question.strip()}".strip()

    def answer(self, question: str, top_n: int = None, history: list = None) -> dict:
        """Responde a la pregunta devolviendo {respuesta, fuentes, used_ai} manteniendo el ancla documental."""
        is_replica = _is_replica_or_correction(question)
        is_followup_q = is_replica or _is_followup(question)

        active_title, active_source = self._get_active_source(history)
        search_query = self._resolve_query(question, history)

        # En seguimientos o consultas cuantitativas se habilita la lectura profunda de documentos
        needs_ocr_call = is_followup_q or search_query != question or _needs_ocr(question)
        results = self.search(search_query, top_n=top_n, enable_ocr=needs_ocr_call)

        # ANCLAJE DE DOCUMENTO ACTIVO:
        # Si venimos de un turno previo y la consulta es un seguimiento o réplica,
        # GARANTIZAR que el documento del que se está hablando sea la fuente prioritaria #1 (results[0]).
        if (is_followup_q or is_replica) and active_source:
            act_url = active_source.get("url")
            existing_idx = next((i for i, r in enumerate(results) if r.get("url") == act_url), None)
            if existing_idx is not None:
                promoted = results.pop(existing_idx)
                results = [promoted] + results
            else:
                results = [active_source] + results

        local = self._local_answer(question, results)
        prompt = self._build_prompt(question, results, history=history)

        order = [self.provider] if self.provider else []
        last_error = ""
        self._init_gemini()
        if self._gemini is not None:
            from google.genai import types as genai_types
            for model_name in GEMINI_MODEL_FALLBACKS:
                try:
                    resp = self._gemini.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            temperature=0.2,
                            max_output_tokens=4500,
                            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                            http_options=genai_types.HttpOptions(timeout=int(GEMINI_TIMEOUT * 1000)),
                        ),
                    )
                    text = (resp.text or "").strip()
                    if text:
                        return {"answer": text, "sources": results,
                                "used_ai": True, "provider": f"gemini ({model_name})"}
                except Exception as e:
                    last_error = str(e)
                    import logging
                    logging.getLogger("fenalco.assistant").warning(f"Error en Google Gemini ({model_name}): {e}")
                    continue

        # Si el modelo falló por cuota, clave inválida, timeout u otro motivo, indicarlo con claridad
        if last_error:
            if "API_KEY_INVALID" in last_error or "INVALID_ARGUMENT" in last_error:
                error_notice = (
                    f"> ⚠️ **Aviso del Servicio de IA:** Google API rechazó la clave configurada (`API_KEY_INVALID`).\n"
                    f"> Verifica la clave en `.env` (Google AI Studio).\n\n"
                )
                return {"answer": error_notice + local, "sources": results, "used_ai": False,
                        "provider": "local (error api key)", "error": last_error}
            elif "RESOURCE_EXHAUSTED" in last_error or "429" in last_error:
                error_notice = (
                    f"> ⏳ **Aviso de cuota de IA:** Se alcanzó el límite temporal de solicitudes por minuto de Google Gemini (Free Tier: 15 peticiones/min). Por favor espera unos segundos y vuelve a consultar.\n\n"
                    f"*Datos extraídos localmente del documento activo mientras se restablece la cuota:* \n\n"
                )
                return {"answer": error_notice + local, "sources": results, "used_ai": False,
                        "provider": "local (cuota temporal agotada)", "error": last_error}
            elif "TIMEOUT" in last_error.upper() or "timed out" in last_error.lower():
                error_notice = (
                    f"> ⏱️ **Aviso de tiempo de espera:** La API de IA tardó más de lo esperado en responder.\n\n"
                    f"*Datos extraídos localmente del documento:* \n\n"
                )
                return {"answer": error_notice + local, "sources": results, "used_ai": False,
                        "provider": "local (timeout)", "error": last_error}

        # Si no hubo respuesta del endpoint, responder con el análisis de documentos
        return {"answer": local, "sources": results, "used_ai": False,
                "provider": "local"}

    # ---------------------------------------- respuesta local (sin API)
    def _local_answer(self, question: str, results: list) -> str:
        if not results:
            return ("No encontré documentos relacionados en la base de datos "
                    "de FENALCO. Intenta con otros términos, por ejemplo "
                    "'salario mínimo', 'tendero', 'vehículos', 'impuesto saludable', "
                    "'reforma laboral' o 'bitácora económica'.")

        r0 = results[0]
        titulo = r0.get("title") or ""
        cat = r0.get("category") or ""
        doc_texts = r0.get("doc_texts") or []

        from .drive_reader import normalize_vertical_words
        full_doc_text = normalize_vertical_words("\n\n".join([dt.get("text", "") for dt in doc_texts if dt.get("text")]))
        doc_filename = (doc_texts[0].get("filename") if doc_texts else "") or "Documento adjunto"
        q_norm = _norm_token(question)
        q_tokens = [t for t in _tokenize(question) if len(t) > 2]

        matched_ocr = []
        if full_doc_text:
            ocr_marker = "--- [DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF] ---"
            if ocr_marker in full_doc_text:
                ocr_body = full_doc_text.split(ocr_marker, 1)[1]
                img_blocks = re.split(r"(?=\[Gráfica|\[Imagen\s+pág\.)", ocr_body)
                for b in img_blocks:
                    b_clean = b.strip()
                    if not b_clean:
                        continue
                    b_norm = _norm_token(b_clean)
                    first_line = b_clean.split("\n", 1)[0]
                    first_norm = _norm_token(first_line)

                    # Palabras no numéricas de la consulta (descartar años para no sesgar)
                    non_year_tokens = [t for t in q_tokens if not t.isdigit() and len(t) > 2]

                    # Coincidencias en el título del gráfico valen 15 puntos cada una
                    title_hits = sum(1 for t in non_year_tokens if t in first_norm)
                    score = title_hits * 15

                    # Coincidencias en el cuerpo valen 2 puntos
                    body_hits = sum(1 for t in non_year_tokens if t in b_norm)
                    score += body_hits * 2

                    # Coincidencias de frases de 2 o 3 palabras consecutivas
                    for phrase_len in (3, 2):
                        for p_idx in range(len(non_year_tokens) - phrase_len + 1):
                            subphrase = " ".join(non_year_tokens[p_idx:p_idx + phrase_len])
                            if subphrase in first_norm:
                                score += 30
                            elif subphrase in b_norm:
                                score += 10

                    if score > 0:
                        matched_ocr.append((score, b_clean))

        if matched_ocr:
            matched_ocr.sort(key=lambda x: -x[0])
            best_ocr_text = matched_ocr[0][1]
            return (
                f"### Datos extraídos de «{titulo}» ({cat})\n\n"
                f"{best_ocr_text}\n\n"
                f"> 📍 **Origen:** Gráfica / Tabla (OCR) en el documento PDF «{doc_filename}» — publicación «{titulo}»."
            )

        # 2. Si no hay OCR específico pero sí texto del documento, buscar párrafos relevantes
        if full_doc_text:
            paras = [p.strip() for p in full_doc_text.split("\n\n") if len(p.strip()) > 50]
            scored_paras = []
            for p in paras:
                p_norm = _norm_token(p)
                score = sum(1 for t in q_tokens if t in p_norm)
                if score >= 2:
                    scored_paras.append((score, p))
            if scored_paras:
                scored_paras.sort(key=lambda x: -x[0])
                top_paras = [p for _, p in scored_paras[:3]]
                page_info = ""
                m_p = re.search(r"--- \[(Página \d+ de \d+)\] ---", top_paras[0])
                if m_p:
                    page_info = f" ({m_p.group(1)})"
                return (
                    f"### Resumen de «{titulo}» ({cat})\n\n"
                    + "\n\n".join(top_paras) +
                    f"\n\n> 📍 **Origen:** Texto digital del documento PDF «{doc_filename}»{page_info} — publicación «{titulo}»."
                )

        # 3. Fallback general con extracto del artículo
        partes = [
            f"Encontré **{len(results)} fuentes coincidentes** con tu consulta. La fuente principal es «{titulo}» ({cat}).",
        ]
        if r0.get("excerpt"):
            partes.append(f"\n> 📍 **Origen:** Registro / Noticia web de FENALCO «{titulo}» ({cat}):\n\n{r0['excerpt'][:600]}...")
        return "\n".join(partes)

    # --------------------------------------------------------------- RESUMIR
    def summarize(self, text: str, title: str = "", doc_texts: list = None) -> str:
        """Genera un resumen ejecutivo del texto/documento dado.

        Combina el cuerpo del artículo con el texto extraído de documentos adjuntos
        (PDFs de Google Drive) y llama a Gemini para producir un resumen en viñetas
        con los puntos clave, cifras más relevantes y conclusiones principales.
        Si la API no está disponible, devuelve un resumen local heurístico.
        """
        # Construir corpus a resumir
        parts = []
        if text and text.strip():
            parts.append(text.strip()[:15000])
        for dt in (doc_texts or []):
            dt_text = (dt.get("text") or "").strip()
            if dt_text:
                fname = dt.get("filename") or "Documento adjunto"
                parts.append(f"[{fname}]\n{dt_text[:8000]}")

        corpus = "\n\n---\n\n".join(parts)
        if not corpus:
            return "_No hay texto disponible para resumir en este registro._"

        titulo_str = f"«{title}»" if title else "este documento"
        prompt = (
            f"Eres un analista experto en economía colombiana y datos de FENALCO.\n"
            f"A continuación tienes el contenido completo de {titulo_str}.\n"
            f"Genera un resumen ejecutivo en español con:\n"
            f"1. **Puntos clave** (máx. 5 viñetas con las ideas y datos más importantes)\n"
            f"2. **Cifras destacadas** (números, porcentajes o estadísticas relevantes si los hay)\n"
            f"3. **Conclusión** (1-2 frases sobre el mensaje principal del documento)\n\n"
            f"Sé preciso, usa los datos del texto, no inventes nada.\n\n"
            f"CONTENIDO A RESUMIR:\n{corpus}"
        )

        self._init_gemini()
        if self._gemini is not None:
            try:
                from google.genai import types as genai_types
                resp = self._gemini.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=1200,
                        thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
                        http_options=genai_types.HttpOptions(timeout=int(GEMINI_TIMEOUT * 1000)),
                    ),
                )
                result = (resp.text or "").strip()
                if result:
                    return result
            except Exception as e:
                import logging
                logging.getLogger("fenalco.assistant").error(f"Error resumiendo con Gemini: {e}")
                if "API_KEY_INVALID" in str(e):
                    return (
                        "> **Error:** La clave de API de Google no es válida. "
                        "Verifica `GEMINI_API_KEY` en el archivo `.env`.\n\n"
                        + self._local_summary(text, title)
                    )

        return self._local_summary(text, title)

    def _local_summary(self, text: str, title: str = "") -> str:
        """Resumen heurístico local cuando Gemini no está disponible."""
        if not text or not text.strip():
            return "_Sin contenido disponible para resumir._"

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 40]
        # Tomar las primeras oraciones y algunas del medio como extracto
        selected = sentences[:3]
        if len(sentences) > 6:
            mid = len(sentences) // 2
            selected += sentences[mid:mid + 2]

        titulo_str = f"**{title}**\n\n" if title else ""
        bullets = "\n".join(f"- {s}" for s in selected[:5])
        total_chars = len(text)
        return (
            f"{titulo_str}"
            f"**Extracto automático** *(resumen local — sin IA disponible)*\n\n"
            f"{bullets}\n\n"
            f"*Documento de {total_chars:,} caracteres. Activa Gemini para un resumen completo.*"
        )


