"""Lector y extractor de documentos de Google Drive y adjuntos para FENALCO.

Permite descargar y extraer el texto de:
- Archivos en Google Drive (PDFs, docs, presentaciones) mediante descarga directa.
- Google Docs (/document/d/...) mediante exportación a texto plano.
- Google Sheets (/spreadsheets/d/...) mediante exportación a CSV.
- Documentos PDF locales o remotos directos.

Mantiene una caché persistente en disco en `output/doc_cache/` para que la
lectura sea instantánea después de la primera descarga.
"""

import io
import json
import logging
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from PIL import Image
except ImportError:
    Image = None


def is_valid_content_image(img_bytes: bytes) -> bool:
    """Valida que una imagen contenga contenido visual sustancial (gráfica o tabla).

    Descarta imágenes demasiado pequeñas (<120x120), sombras transparentes o imágenes
    con contraste casi nulo (colores planos decorativos, marcos o plantillas vacías).
    """
    if not img_bytes or len(img_bytes) < 8000:
        return False
    if Image is None:
        return True
    try:
        im = Image.open(io.BytesIO(img_bytes))
        w, h = im.size
        # Descarta banners diminutos, íconos, sombras o separadores
        if w < 120 or h < 120:
            return False
        # Descarta imágenes casi transparentes (sombras o máscaras de recorte)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            im_rgba = im.convert("RGBA")
            alpha = im_rgba.split()[-1]
            if alpha.getextrema()[1] < 60:
                return False
        # Descarta imágenes planas sin contraste (fondos monocromáticos)
        im_gray = im.convert("L")
        extrema = im_gray.getextrema()
        if extrema[1] - extrema[0] < 20:
            return False
        return True
    except Exception:
        return False


def normalize_vertical_words(text: str) -> str:
    """Normaliza texto donde cada palabra quedó en una línea separada por la extracción del PDF."""
    if not text:
        return ""
    lines = text.splitlines()
    non_empty = [l.strip() for l in lines if l.strip()]
    if len(non_empty) > 25 and (sum(len(l) for l in non_empty) / len(non_empty)) < 16:
        import re
        text = re.sub(r"(--- \[Página \d+ de \d+\] ---)", r"\n\n\1\n\n", text)
        text_norm = re.sub(r"(?:[ \t]*\r?\n){3,}", "\n\n", text)
        paras = text_norm.split("\n\n")
        cleaned_paras = []
        for p in paras:
            p_strip = p.strip()
            if not p_strip:
                continue
            if p_strip.startswith("--- ["):
                cleaned_paras.append(p_strip)
            else:
                words = p_strip.split()
                cleaned_paras.append(" ".join(words))
        return "\n\n".join(cleaned_paras)
    return text

logger = logging.getLogger("fenalco.drive_reader")

# Directorio de caché persistente
_CACHE_DIR = Path(__file__).resolve().parents[2] / "output" / "doc_cache"
_INDEX_FILE = _CACHE_DIR / "index.json"

# Directorio donde se guardan las imágenes extraídas de los PDFs (p. ej. gráficas)
# para que el asistente pueda mostrarlas y abrirlas en pantalla completa.
_IMGS_DIR = Path(__file__).resolve().parents[2] / "output" / "doc_imgs"

# Marca dentro del texto extraído que referencia una imagen guardada en disco.
# Formato: [[IMG:<url>/<doc_id>/<archivo>|<subtítulo>]]
IMAGE_MARKER_RE = re.compile(r"\[\[IMG:(?P<src>[^|\]]+)\|(?P<caption>[^\]]*)\]\]")

# IDs conocidos de avisos de privacidad / tratamiento de datos genéricos que aparecen en footers
GENERIC_PRIVACY_IDS = {
    "1mEI9zB7G7TKvCXlYL_GIwkg5hPqQboGZ",
    "1U9YEq8WFInXZP7LasuuZ4c0jG6Y0aM1J",
    "1hK-GGbOVwLPA8BUyxOVH20KedYz7551B",
    "1bzxJWeB_AgdgGKpRUxS7O4sS3I_k-fmZ",
    "1SGsRi9F1rGVzSzbwl4d1pPSZFuoNmJHh",
    "1LohLazFJyx2u3FqUqxg7CfAc0kJNC32l",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

import hashlib
import os
OCR_TIMEOUT = float(os.environ.get("GEMINI_TIMEOUT", 120))     # segundos máximos por llamada OCR a la API de visión
MAX_OCR_PAGES = 50    # páginas máximas de un PDF en las que se busca texto/imágenes
MAX_OCR_IMAGES = 45   # imágenes máximas con OCR por cada PDF


def clean_spaced_name(name: str) -> str:
    """Normaliza nombres que tienen letras separadas por espacios.
    
    Ejemplo: 'T r a t a m i e n t o   d e   D a t o s' -> 'Tratamiento de Datos'
    """
    if not name:
        return ""
    name = re.sub(r"[\xa0\u200b\t]+", " ", name).strip()
    words = [w.strip() for w in re.split(r"\s{2,}", name) if w.strip()]
    cleaned_words = []
    for w in words:
        tokens = w.split(" ")
        if len(tokens) >= 2 and all(len(t) == 1 for t in tokens):
            cleaned_words.append("".join(tokens))
        else:
            cleaned_words.append(w)
    return " ".join(cleaned_words).strip()



def extract_drive_id(url: str) -> str:
    """Extrae el ID único del archivo o documento de Google Drive."""
    if not url:
        return ""
    url = url.strip()

    # /file/d/<id>
    m = re.search(r"/file/d/([a-zA-Z0-9_-]{20,})", url)
    if m:
        return m.group(1)

    # /document/d/<id>
    m = re.search(r"/document/d/([a-zA-Z0-9_-]{20,})", url)
    if m:
        return m.group(1)

    # /spreadsheets/d/<id>
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]{20,})", url)
    if m:
        return m.group(1)

    # ?id=<id> o &id=<id>
    m = re.search(r"[?&]id=([a-zA-Z0-9_-]{20,})", url)
    if m:
        return m.group(1)

    # Hash o id genérico en URL
    m = re.search(r"/d/([a-zA-Z0-9_-]{20,})", url)
    if m:
        return m.group(1)

    return ""


class DriveReader:
    """Gestiona la lectura, descarga y almacenamiento en caché de documentos."""

    def __init__(self, cache_dir: Path = _CACHE_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.cache_dir / "index.json"
        self._index = self._load_index()
        # Caché en memoria para evitar accesos repetidos a disco
        self._mem_cache = {}

    def _load_index(self) -> dict:
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error cargando índice de documentos: {e}")
        return {}

    def _save_index(self):
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error guardando índice de documentos: {e}")

    def is_cached(self, doc_id: str) -> bool:
        """Indica si el documento ya fue extraído y está en caché."""
        if not doc_id:
            return False
        cache_path = self.cache_dir / f"{doc_id}.txt"
        return cache_path.exists() and cache_path.stat().st_size > 0

    def get_cached_text(self, doc_id: str) -> str | None:
        """Devuelve el texto en caché si existe."""
        if not doc_id:
            return None
        if doc_id in self._mem_cache:
            return self._mem_cache[doc_id]
        cache_path = self.cache_dir / f"{doc_id}.txt"
        if cache_path.exists():
            try:
                text = cache_path.read_text(encoding="utf-8")
                self._mem_cache[doc_id] = text
                return text
            except Exception:
                pass
        return None

    def save_to_cache(self, doc_id: str, text: str, meta: dict = None):
        """Guarda el texto y metadatos de un documento en la caché."""
        if not doc_id or not text:
            return
        text = text.strip()
        if not text:
            return
        cache_path = self.cache_dir / f"{doc_id}.txt"
        try:
            cache_path.write_text(text, encoding="utf-8")
            self._mem_cache[doc_id] = text
            meta_entry = {
                "chars": len(text),
                "title": (meta or {}).get("filename", ""),
                "url": (meta or {}).get("url", ""),
            }
            self._index[doc_id] = meta_entry
            self._save_index()
        except Exception as e:
            logger.warning(f"Error guardando caché de {doc_id}: {e}")

    def _open_fitz(self, data: bytes):
        """Abre un PDF con PyMuPDF (fitz) para poder rasterizar páginas.

        Devuelve None si PyMuPDF no está instalado o falla.
        """
        try:
            import pymupdf  # PyMuPDF (también expone el alias fitz)
            return pymupdf.open(stream=data, filetype="pdf")
        except Exception as e:
            logger.debug(f"PyMuPDF no disponible/falló: {e}")
            return None

    def _page_has_vector_graphics(self, fitz_doc, page_index: int) -> bool:
        """True si la página contiene trazas de dibujo (líneas, rectángulos,
        curvas), típico de gráficas de líneas/barras vectoriales."""
        try:
            if fitz_doc is None or page_index is None:
                return False
            if page_index >= fitz_doc.page_count:
                return False
            page = fitz_doc.load_page(page_index)
            drawings = page.get_drawings()
            return len(drawings) > 0
        except Exception as e:
            logger.debug(f"_page_has_vector_graphics: {e}")
            return False

    def _render_page(self, fitz_doc, page_index: int, dpi: int = 150) -> bytes:
        """Rasteriza una página del PDF a PNG (bytes). Captura también gráficos
        vectoriales que no son imágenes incrustadas extraíbles."""
        try:
            import pymupdf  # PyMuPDF
            if fitz_doc is None or page_index >= fitz_doc.page_count:
                return b""
            page = fitz_doc.load_page(page_index)
            matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=matrix, colorspace=pymupdf.csRGB, alpha=False)
            return pix.tobytes("png")
        except Exception as e:
            logger.warning(f"No se pudo rasterizar la página {page_index + 1}: {e}")
            return b""

    def _save_doc_image(self, doc_id: str, page_no: int, img_name: str,
                        img_bytes: bytes, mime: str) -> str:
        """Guarda una imagen extraída del PDF y devuelve su URL relativa.

        La URL relativa (/doc-img/<doc_id>/<archivo>) la sirve el servidor web
        para que el asistente pueda incrustarla y abrirla en pantalla completa.
        """
        folder = _IMGS_DIR / doc_id
        folder.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", (img_name or "img"))
        if not safe or safe == "img":
            safe = f"img_{page_no}_{int(time.time() * 1000) % 100000}"
        ext = ".jpg" if mime == "image/jpeg" else ".png"
        filename = f"p{page_no}_{safe}{ext}"
        # No sobrescribir innecesariamente si ya existe (idempotente)
        path = folder / filename
        if not path.exists():
            try:
                path.write_bytes(img_bytes)
            except Exception as e:
                logger.warning(f"No se pudo guardar la imagen {filename}: {e}")
        return f"/doc-img/{doc_id}/{filename}"

    def _ocr_image(self, img_bytes: bytes, mime: str = "image/png",
                   ocr_deadline: float | None = None) -> str:
        """Transcribe una imagen usando Gemini Vision con filtro estricto anti-alucinaciones."""
        from .assistant import GEMINI_KEY, GEMINI_MODEL_FALLBACKS
        if not img_bytes:
            logger.debug("OCR: imagen vacía, se omite")
            return ""
        if not is_valid_content_image(img_bytes):
            logger.debug("OCR: imagen descartada por no tener contraste suficiente o ser decorativa/minúscula")
            return ""
        if not GEMINI_KEY:
            logger.warning("OCR: GEMINI_API_KEY no está configurada — no se puede hacer OCR de imágenes")
            return ""
        if ocr_deadline is not None and time.monotonic() > ocr_deadline:
            return ""
        try:
            from google.genai import Client, types
            client = Client(
                api_key=GEMINI_KEY,
                http_options=types.HttpOptions(timeout=int(OCR_TIMEOUT * 1000)),
            )
            gen_config = types.GenerateContentConfig(
                temperature=0.0,
                system_instruction=(
                    "Eres un transcriptor forense de datos e imágenes de documentos. "
                    "Tu única tarea es transcribir única y exclusivamente los datos que estén legibles y visibles en la imagen de forma exacta. "
                    "PROHIBIDO inventar, suponer, deducir o proyectar datos que no estén impresos explícitamente. "
                    "Si no hay datos claros ni texto informativo legible, responde EXACTAMENTE: [DECORATIVO]."
                ),
            )
            prompt = (
                "Actúa como un transcriptor forense de documentos y analista de datos.\n"
                "En esta imagen puede haber un gráfico (barras, circular/dona, líneas), tabla, infografía, diagrama o texto de una presentación o informe.\n"
                "Instrucciones obligatorias:\n"
                "1. Si la imagen es SOLO un fondo decorativo, marco, plantilla vacía, sombra, patrón, logo aislado o diseño sin datos ni texto informativo legible, responde EXACTAMENTE: [DECORATIVO]\n"
                "2. Si contiene un GRÁFICO o TABLA con cifras legibles:\n"
                "   - Indica el TÍTULO del gráfico en negrita al inicio.\n"
                "   - Transcribe todas las categorías, etiquetas y sus porcentajes o cifras exactas visibles (ej. Propietario: 73.18%, Estrato 1: 36.82%).\n"
                "   - Transcribe notas explicativas visibles si existen.\n"
                "3. Si contiene TEXTO o PÁRRAFO: transcribe todo el texto de forma fiel y completa.\n"
                "4. NUNCA inventes números ni series históricas que no aparezcan con total claridad en la imagen.\n"
                "Responde directamente en español con la información extraída."
            )
            for model_name in GEMINI_MODEL_FALLBACKS:
                if ocr_deadline is not None and time.monotonic() > ocr_deadline:
                    break
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=img_bytes, mime_type=mime),
                            prompt,
                        ],
                        config=gen_config,
                    )
                    txt = (resp.text or "").strip()
                    if txt:
                        if "[DECORATIVO]" in txt.upper() or txt.strip() == "[DECORATIVO]":
                            return ""
                        logger.info(f"OCR exitoso con {model_name}: {len(txt)} caracteres")
                        return txt
                except Exception as ocr_err:
                    logger.debug(f"OCR falló con {model_name}: {ocr_err}")
                    continue
        except Exception as e:
            logger.warning(f"Error en OCR con Gemini Vision: {e}")
        return ""

    def extract_text_from_pdf_bytes(self, data: bytes, enable_ocr: bool = True,
                                    ocr_deadline: float | None = None,
                                    doc_id: str = "") -> str:
        """Extrae el texto de un archivo PDF en memoria, combinando texto digital y OCR de las imágenes.

        Estrategia optimizada:
        - Extrae texto digital etiquetando el número de página de forma inequívoca.
        - Deduplica imágenes por hash MD5 para no reprocesar plantillas/fondos repetidos en varias páginas.
        - Descarta plantillas decorativas vacías.
        - Procesa imágenes de datos en paralelo para máxima velocidad y exhaustividad.
        """
        if not data:
            return ""
        if pypdf is None:
            logger.warning("pypdf no está disponible")
            return ""
        try:
            reader = pypdf.PdfReader(io.BytesIO(data))
            total_pages = len(reader.pages)
            text_parts = []
            ocr_sections = []

            # fitz (PyMuPDF) para gráficos vectoriales si aplica
            fitz_doc = self._open_fitz(data)

            # 1. Extraer texto digital página por página (preferir fitz para texto continuo)
            for i, page in enumerate(reader.pages):
                if i >= MAX_OCR_PAGES:
                    break
                txt = ""
                if fitz_doc is not None and i < len(fitz_doc):
                    try:
                        txt = (fitz_doc[i].get_text("text") or "").strip()
                    except Exception:
                        txt = ""
                if not txt:
                    txt = (page.extract_text() or "").strip()

                txt = normalize_vertical_words(txt)
                if txt:
                    text_parts.append(f"--- [Página {i+1} de {total_pages}] ---\n{txt}")

            # 2. Recolectar imágenes candidatas deduplicadas por hash MD5
            raw_candidates = []
            seen_hashes = set()
            pages_with_raster = set()

            if enable_ocr:
                for i, page in enumerate(reader.pages):
                    if i >= MAX_OCR_PAGES:
                        break
                    try:
                        images = list(getattr(page, "images", []))
                        for img in images:
                            if not img.data or len(img.data) < 8000:
                                continue
                            if not is_valid_content_image(img.data):
                                continue
                            h = hashlib.md5(img.data).hexdigest()
                            if h in seen_hashes:
                                pages_with_raster.add(i)
                                continue
                            seen_hashes.add(h)
                            pages_with_raster.add(i)
                            ext = img.name.lower()
                            mime = "image/png" if ext.endswith(".png") else "image/jpeg"
                            raw_candidates.append({
                                "page_no": i + 1,
                                "name": img.name,
                                "data": img.data,
                                "mime": mime,
                                "hash": h,
                            })
                            if len(raw_candidates) >= MAX_OCR_IMAGES:
                                break
                    except Exception as img_err:
                        logger.debug(f"Error explorando imágenes página {i+1}: {img_err}")
                    if len(raw_candidates) >= MAX_OCR_IMAGES:
                        break

            # 2b. Añadir gráficos vectoriales para páginas que no tuvieron imágenes raster válidas
            if enable_ocr and fitz_doc is not None and len(raw_candidates) < MAX_OCR_IMAGES:
                for i in range(min(total_pages, MAX_OCR_PAGES)):
                    if i in pages_with_raster:
                        continue
                    if self._page_has_vector_graphics(fitz_doc, i):
                        png_bytes = self._render_page(fitz_doc, i)
                        if png_bytes and len(png_bytes) >= 8000 and is_valid_content_image(png_bytes):
                            h = hashlib.md5(png_bytes).hexdigest()
                            if h not in seen_hashes:
                                seen_hashes.add(h)
                                raw_candidates.append({
                                    "page_no": i + 1,
                                    "name": f"page_{i+1}_vector",
                                    "data": png_bytes,
                                    "mime": "image/png",
                                    "hash": h,
                                })
                    if len(raw_candidates) >= MAX_OCR_IMAGES:
                        break

            # 3. Procesar OCR en paralelo (hasta 4 hilos) para no superar timeouts
            if raw_candidates and (ocr_deadline is None or time.monotonic() <= ocr_deadline):
                def _do_ocr_task(cand):
                    if ocr_deadline is not None and time.monotonic() > ocr_deadline:
                        return None
                    src = self._save_doc_image(
                        doc_id or "doc", cand["page_no"], cand["name"], cand["data"], cand["mime"])
                    txt = self._ocr_image(cand["data"], mime=cand["mime"], ocr_deadline=ocr_deadline)
                    if txt and txt.strip() and "[DECORATIVO]" not in txt.upper():
                        return {
                            "page_no": cand["page_no"],
                            "name": cand["name"],
                            "text": txt.strip(),
                            "src": src,
                        }
                    return None

                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [pool.submit(_do_ocr_task, c) for c in raw_candidates]
                    for fut in as_completed(futures):
                        try:
                            res = fut.result()
                            if res:
                                ocr_sections.append(
                                    f"[Gráfica/visual pág. {res['page_no']} — {res['name']}]:\n{res['text']}"
                                    f"\n[[IMG:{res['src']}|Gráfica pág. {res['page_no']}]]"
                                )
                        except Exception as fut_err:
                            logger.debug(f"Error procesando OCR individual: {fut_err}")

            # Ordenar secciones OCR por número de página
            def _get_page(sec):
                m = re.search(r"pág\.\s+(\d+)", sec)
                return int(m.group(1)) if m else 999
            ocr_sections.sort(key=_get_page)

            parts = text_parts
            if ocr_sections:
                ocr_block = (
                    "\n\n--- [DATOS EXTRAÍDOS DE IMÁGENES DENTRO DEL PDF] ---\n"
                    + "\n\n".join(ocr_sections)
                )
                parts = text_parts + [ocr_block]
                logger.info(f"OCR completado: {len(ocr_sections)} imagen(es) con datos procesadas de {total_pages} páginas")

            try:
                if fitz_doc is not None:
                    fitz_doc.close()
            except Exception:
                pass
            return "\n\n".join(parts)
        except Exception as e:
            logger.warning(f"Error extrayendo texto del PDF: {e}")
            return ""

    def download_and_extract(self, url: str, timeout: float = 8.0,
                             enable_ocr: bool = True,
                             ocr_deadline: float | None = None) -> str:
        """Descarga el documento de Google Drive o web y extrae su texto."""
        if not url:
            return ""

        doc_id = extract_drive_id(url)
        # Si ya está en caché, devolver inmediatamente
        if doc_id:
            cached = self.get_cached_text(doc_id)
            if cached is not None:
                return cached

        # Estrategias de descarga según el tipo de URL
        endpoints = []
        is_gdoc = "docs.google.com/document" in url
        is_gsheet = "docs.google.com/spreadsheets" in url

        if is_gdoc and doc_id:
            endpoints.append(f"https://docs.google.com/document/d/{doc_id}/export?format=txt")
        elif is_gsheet and doc_id:
            endpoints.append(f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv")
        elif doc_id:
            # Endpoints de descarga directa de Google Drive
            endpoints.append(f"https://drive.usercontent.google.com/download?id={doc_id}&export=download")
            endpoints.append(f"https://drive.google.com/uc?export=download&id={doc_id}")
            endpoints.append(f"https://docs.google.com/uc?export=download&id={doc_id}")
        else:
            # URL web directa (ej. https://.../documento.pdf)
            endpoints.append(url)

        headers = {"User-Agent": USER_AGENT}

        for ep in endpoints:
            try:
                req = urllib.request.Request(ep, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    status = resp.status
                    if status != 200:
                        continue
                    content_type = resp.headers.get("Content-Type", "").lower()
                    raw_bytes = resp.read()

                    # Verificar si es PDF
                    if raw_bytes[:4] == b"%PDF" or "application/pdf" in content_type:
                        text = self.extract_text_from_pdf_bytes(
                            raw_bytes, enable_ocr=enable_ocr, ocr_deadline=ocr_deadline,
                            doc_id=doc_id)
                    elif "text/" in content_type or is_gdoc or is_gsheet:
                        try:
                            text = raw_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            text = raw_bytes.decode("latin-1", errors="ignore")
                    else:
                        # Si parece binario, intentar como PDF
                        if b"%PDF" in raw_bytes[:1024]:
                            text = self.extract_text_from_pdf_bytes(
                                raw_bytes, enable_ocr=enable_ocr, ocr_deadline=ocr_deadline,
                                doc_id=doc_id)
                        else:
                            try:
                                text = raw_bytes.decode("utf-8")
                            except Exception:
                                text = ""

                    if text and len(text.strip()) > 30:
                        clean = text.strip()
                        if doc_id:
                            self.save_to_cache(doc_id, clean, {"url": url})
                        return clean
            except Exception as exc:
                logger.debug(f"Fallo descarga desde {ep}: {exc}")
                continue

        return ""

    def get_document_text(self, url: str, timeout: float = 6.0,
                          force_ocr: bool = False, enable_ocr: bool = True,
                          ocr_deadline: float | None = None) -> str:
        """Obtiene el texto de un documento (desde caché o descargándolo).
        
        Si force_ocr=True y el texto cacheado no contiene sección OCR,
        se re-descarga y re-extrae para incluir imágenes.
        enable_ocr controla si la extracción aplica OCR/visión a las imágenes
        del PDF (solo con consultas de datos que lo necesiten).
        """
        doc_id = extract_drive_id(url)
        if doc_id:
            cached = self.get_cached_text(doc_id)
            if cached is not None:
                # ¿El caché incluye imágenes/marcas? Un caché con la sección "DATOS
                # EXTRAÍDOS DE IMÁGENES" pero SIN marcas [[IMG:]] ni imágenes en disco
                # es antiguo (generado antes de guardar imágenes): hay que re-extraer.
                has_ocr_section = "DATOS EXTRAÍDOS DE IMÁGENES" in cached
                has_img_markers = bool(IMAGE_MARKER_RE.search(cached))
                has_disk_imgs = bool(self._list_saved_doc_images(doc_id))
                cache_complete = bool(has_img_markers or has_disk_imgs)
                # Un caché es legacy si tiene OCR antiguo pero no incluye los nuevos marcadores
                # de páginas '--- [Página X de Y] ---' introducidos en el motor moderno.
                is_legacy = bool("--- [Página" not in cached and has_ocr_section)
                if not is_legacy and has_ocr_section and cache_complete:
                    return cached

                # Re-extraer con OCR completo si se pide force_ocr, si el caché está incompleto,
                # o si es un documento legacy que requiere el nuevo estándar de páginas y deduplicación.
                need_ocr = force_ocr or (enable_ocr and not cache_complete) or (enable_ocr and is_legacy)
                if need_ocr:
                    logger.info(f"Re-extrayendo {doc_id} con nuevo motor de OCR, páginas y deduplicación")
                    cache_path = self.cache_dir / f"{doc_id}.txt"
                    try:
                        cache_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    self._mem_cache.pop(doc_id, None)
                else:
                    return cached
        return self.download_and_extract(url, timeout=timeout,
                                         enable_ocr=enable_ocr,
                                         ocr_deadline=ocr_deadline)

    def _list_saved_doc_images(self, doc_id: str) -> list:
        """Devuelve las imágenes ya guardadas en disco para un doc_id (sin re-OCR).

        Útil para documentos cacheados antes de existir las marcas [[IMG:...]],
        de modo que sigan mostrando sus gráficas sin volver a descargar/leer.
        """
        if not doc_id:
            return []
        folder = _IMGS_DIR / doc_id
        if not folder.is_dir():
            return []
        images = []
        for p in sorted(folder.glob("*")):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
                images.append({
                    "src": f"/doc-img/{doc_id}/{p.name}",
                    "caption": f"Imagen extraída del documento ({p.name})",
                })
        return images

    def get_record_documents_text(
        self, record: dict, max_docs: int = 4, timeout: float = 5.0,
        skip_privacy: bool = True, enable_ocr: bool = True
    ) -> list:
        """Devuelve una lista con el texto extraído de los documentos de un registro.
        
        Prioriza documentos sustanciales sobre políticas genéricas de tratamiento de datos.
        La extracción de una página trata como PDF cuando enable_ocr=True; en caso de
        documentos ya cacheados, la caché se sirve al instante.
        """
        docs = record.get("documents") or []
        if not docs:
            return []

        # Separar y ordenar documentos: sustanciales primero
        substantive = []
        generic = []
        for d in docs:
            u = d.get("url") or ""
            doc_id = extract_drive_id(u)
            raw_name = d.get("filename") or ""
            clean_name = clean_spaced_name(raw_name)

            is_priv = (
                doc_id in GENERIC_PRIVACY_IDS
                or "tratamiento datos" in clean_name.lower()
                or "tratamiento de datos" in clean_name.lower()
                or "autorizo tratamiento" in clean_name.lower()
            )
            item = {
                "url": u,
                "doc_id": doc_id,
                "filename": clean_name or "Documento adjunto",
                "is_generic": is_priv,
            }
            if is_priv:
                generic.append(item)
            else:
                substantive.append(item)

        candidates = substantive if (substantive or not skip_privacy) else generic
        candidates = candidates[:max_docs]

        # Presupuesto de tiempo global: la lectura/OCR nunca debe colgar la app.
        # Como máximo dedicamos 2x el timeout de cada documento a la descarga/OCR.
        fetch_deadline = time.monotonic() + (timeout * 2)

        results = []
        for item in candidates:
            if time.monotonic() > fetch_deadline:
                break
            # force_ocr=False: si hay caché se sirve al instante; si el documento
            # no estaba cacheado, se descarga y se aplica OCR acotado (timeout y
            # límites de páginas/imágenes) respetando el presupuesto global.
            # enable_ocr indica si hace falta visión/OCR (solo consultas de datos).
            text = self.get_document_text(
                item["url"], timeout=timeout, force_ocr=False,
                enable_ocr=enable_ocr, ocr_deadline=fetch_deadline,
            )
            if text:
                # Extraer las imágenes referenciadas en el texto y quitarlas de él
                # (las marcas no deben alimentar el prompt, solo la UI).
                images = []
                clean_text = IMAGE_MARKER_RE.sub("", text)
                for m in IMAGE_MARKER_RE.finditer(text):
                    images.append({
                        "src": m.group("src").strip(),
                        "caption": m.group("caption").strip(),
                    })
                # Añadir también imágenes ya guardadas en disco (cachés antiguas sin marcas)
                seen = {im["src"] for im in images}
                for im in self._list_saved_doc_images(item["doc_id"]):
                    if im["src"] not in seen:
                        images.append(im)
                results.append({
                    "url": item["url"],
                    "filename": item["filename"],
                    "doc_id": item["doc_id"],
                    "text": clean_text,
                    "images": images,
                })

        return results

    def get_cached_count(self) -> int:
        """Devuelve cuántos documentos están actualmente en caché."""
        return len(list(self.cache_dir.glob("*.txt")))

    def get_all_cached_texts(self) -> dict:
        """Devuelve un mapa {doc_id: text} con todos los textos cacheados."""
        res = {}
        for txt_file in self.cache_dir.glob("*.txt"):
            doc_id = txt_file.stem
            try:
                res[doc_id] = txt_file.read_text(encoding="utf-8")
            except Exception:
                pass
        return res


# Instancia singleton para toda la aplicación
drive_reader = DriveReader()


def batch_cache_top_documents(records: list, max_records: int = 150, max_workers: int = 6):
    """Descarga en segundo plano documentos de los registros más recientes o relevantes."""
    reader = DriveReader()
    to_download = []
    seen_ids = set()

    for r in records[:max_records]:
        for d in r.get("documents") or []:
            u = d.get("url") or ""
            doc_id = extract_drive_id(u)
            if not doc_id or doc_id in seen_ids or doc_id in GENERIC_PRIVACY_IDS:
                continue
            if not reader.is_cached(doc_id):
                seen_ids.add(doc_id)
                to_download.append((doc_id, u, d.get("filename", "")))

    if not to_download:
        return 0

    logger.info(f"Iniciando descarga en segundo plano de {len(to_download)} documentos...")
    success = 0

    def _worker(item):
        doc_id, url, name = item
        txt = reader.download_and_extract(url, timeout=10.0)
        return bool(txt)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_worker, it) for it in to_download]
        for f in as_completed(futures):
            try:
                if f.result():
                    success += 1
            except Exception:
                pass

    logger.info(f"Descarga finalizada: {success}/{len(to_download)} documentos cacheados.")
    return success


if __name__ == "__main__":
    import sys
    print(f"Documentos en caché: {drive_reader.get_cached_count()}")
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        print(f"Probando descarga de {test_url}...")
        t = drive_reader.get_document_text(test_url)
        print(f"Resultado: {len(t)} caracteres extraídos")
        print("Muestra:", t[:300])
