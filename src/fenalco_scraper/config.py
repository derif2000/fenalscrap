"""Configuración global del scraper de FENALCO."""

from pathlib import Path

# Rutas del proyecto
BASE_DIR = Path(__file__).resolve().parents[2]          # .../scraphanwen
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
DOWNLOADS_DIR = OUTPUT_DIR / "downloads"

# URL base y recursos
SITE = "https://www.fenalco.com.co"
SITEMAP_URL = SITE + "/sitemap.xml"
ROBOTS_URL = SITE + "/robots.txt"

# Archivos intermedios
SITEMAP_FILE = DATA_DIR / "sitemap.xml"
URLS_FILE = DATA_DIR / "urls.txt"
CMS_URLS_FILE = DATA_DIR / "cms_urls.txt"
DONE_FILE = OUTPUT_DIR / ".done.txt"            # checkpoint para reanudar
RECORDS_FILE = OUTPUT_DIR / "fenalco_pages.jsonl"  # registros extraídos

# HTTP
TIMEOUT = 30                     # segundos por petición
MAX_RETRIES = 4                  # reintentos ante fallos de red
RETRY_BACKOFF = 2.5              # base (segundos) para backoff exponencial

# Comportamiento por defecto del crawler
DEFAULT_WORKERS = 6              # hilos concurrentes
DEFAULT_DELAY = 0.4              # pausa base (seg) entre peticiones por hilo

# Categorías del blog (id -> nombre descriptivo)
BLOG_CATEGORIES = {
    "juridico-2": "Jurídico (NotiJurídicos)",
    "noticias-10": "Noticias",
    "economico-3": "Económico",
    "gremial-4": "Gremial",
    "sectores-22": "Sectores",
    "tecnologia-28": "Tecnología",
    "servicios-21": "Servicios",
    "informes-de-gestion-1257": "Informes de Gestión",
    "casa-fenalco-6": "Casa Fenalco",
    "beneficios-26": "Beneficios",
    "jr-1266": "Jr / Sala de Prensa",
}

# Extensiones de documentos adjuntos que interesan
DOC_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".csv", ".txt", ".png", ".jpg", ".jpeg",
)