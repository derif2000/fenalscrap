"""Orquestación del scraping: pool de hilos, límite de tasa, reanudación
y persistencia incremental a un archivo JSONL."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .extractor import extract_page
from .session import build_session, fetch_html, polite_sleep


class FenalcoScraper:
    """Descarga todas las URLs del sitemap y extrae registros estructurados."""

    def __init__(self, workers=None, delay=None, resume=True):
        self.workers = workers or config.DEFAULT_WORKERS
        self.delay = config.DEFAULT_DELAY if delay is None else delay
        self.resume = resume
        self._lock = threading.Lock()
        self._count = 0
        self._errors = 0
        self._start = time.time()

    # ---------------------------------------------------------- utilidades
    def _load_done(self):
        if not config.DONE_FILE.exists():
            return set()
        return set(config.DONE_FILE.read_text(encoding="utf-8").splitlines())

    def _mark_done(self, url):
        with self._lock:
            with open(config.DONE_FILE, "a", encoding="utf-8") as f:
                f.write(url + "\n")

    def _log_record(self, record: dict):
        with self._lock:
            with open(config.RECORDS_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _progress(self, total):
        elapsed = max(time.time() - self._start, 0.001)
        rate = self._count / elapsed
        remaining = (total - self._count) / rate if rate else 0
        msg = (f"[{self._count}/{total}] errores={self._errors} "
               f"velocidad={rate:.1f}/s ETA={remaining/60:.1f}min")
        if self._count % 25 == 0 or self._count == total:
            print(msg, flush=True)

    # ------------------------------------------------------------- trabajo
    def _process(self, entry, done):
        url = entry["url"]
        if self.resume and url in done:
            return None
        polite_sleep(self.delay)
        try:
            html, status, final_url = fetch_html(self._session, url)
            if status != 200:
                raise RuntimeError(f"HTTP {status}")
            # Páginas auxiliares de Odoo suelen redirigir al login
            if "Iniciar sesión" in html[:4000] and final_url != url \
                    and "portal" in final_url and entry["kind"] == "aux":
                return None
            record = extract_page(
                html, final_url,
                kind=entry["kind"],
                category=entry["category"],
                lastmod=entry["lastmod"],
            )
            return url, record
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                self._errors += 1
                if self._errors <= 20:
                    print(f"  ! error {url}: {exc}")
            return url, None

    # ----------------------------------------------------------- ejecución
    def run(self, entries, limit=None):
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        done = self._load_done() if self.resume else set()
        todo = [e for e in entries if e["url"] not in done]

        if limit is not None and limit > 0:
            todo = todo[:limit]

        print(f"[crawler] Total={len(entries)} Pendientes={len(todo)} "
              f"Ya_scrapeadas={len(done)} "
              f"(limit aplicado: {len(entries)-len(done)-len(todo)} omitidas) "
              f"Hilos={self.workers} Resumen={self.resume}")

        self._session = build_session()
        self._count = 0
        self._errors = 0

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            prev = {}
            futures = {pool.submit(self._process, e, done): e for e in todo}
            # map para conservar el orden de 'todo' en la salida
            buf = {}
            for fut in as_completed(futures):
                result = fut.result()
                if result is None:
                    continue
                url, record = result
                if record:
                    self._log_record(record)
                    self._count += 1
                    self._mark_done(url)
                else:
                    self._count += 1  # contamos como procesada aunque fallara
                    self._mark_done(url)
                self._progress(len(todo))

        elapsed = time.time() - self._start
        print(f"[crawler] Terminado: {self._count} procesadas, "
              f"{self._errors} errores, en {elapsed/60:.1f} min")
