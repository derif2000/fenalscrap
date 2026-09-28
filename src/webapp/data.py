"""Carga de datos, filtrado, ordenamiento y paginación de la app web."""

import json
from pathlib import Path

import pandas as pd

from .search import FenalcoSearchEngine

KIND_LABELS = {
    "blog-post": "Blog / Noticia",
    "cms": "Página / CMS",
    "event": "Evento",
}

_TIPO = {
    "Blog / Noticia": "blog-post",
    "Página / CMS": "cms",
    "Evento": "event",
}

_RECORDS_FILE = Path(__file__).resolve().parents[2] / "output" / "fenalco_all.json"


def _load_records() -> list:
    if not _RECORDS_FILE.exists():
        raise FileNotFoundError(
            "No se encontró output/fenalco_all.json. Ejecuta primero python run.py "
            "y luego python export.py para generarlo.")
    with open(_RECORDS_FILE, encoding="utf-8") as f:
        return json.load(f)


class FenalcoData:
    """Mantiene en memoria los registros extraídos y su índice por URL."""

    def __init__(self):
        self.records = _load_records()
        self.by_url = {r["url"]: r for r in self.records}
        self.df = self._build_frame(self.records)
        self.search_engine = FenalcoSearchEngine(self.records)
        self._init_collections()

    def reload(self):
        """Recarga los registros desde output/fenalco_all.json en memoria."""
        self.records = _load_records()
        self.by_url = {r["url"]: r for r in self.records}
        self.df = self._build_frame(self.records)
        self.search_engine = FenalcoSearchEngine(self.records)
        self._init_collections()

    def _init_collections(self):
        import re
        self._docs = []
        self._imgs = []
        cat_agg = {}

        for r in self.records:
            cat = r.get("category") or "Sin categoría"
            if cat not in cat_agg:
                cat_agg[cat] = {"category": cat, "records": 0, "documents": 0, "images": 0}
            cat_agg[cat]["records"] += 1

            # Documentos
            docs = r.get("documents") or []
            cat_agg[cat]["documents"] += len(docs)
            for d in docs:
                raw_name = d.get("filename") or ""
                clean_name = re.sub(r"[\s\xa0\u200b]+", " ", raw_name).strip()
                if not clean_name:
                    clean_name = "Documento adjunto"
                self._docs.append({
                    "filename": clean_name,
                    "url": d.get("url") or "",
                    "article_title": r.get("title") or "Sin título",
                    "article_url": r.get("url") or "",
                    "category": cat,
                    "date": r.get("publish_date") or "",
                    "kind": r.get("kind") or "",
                })

            # Imágenes
            imgs = r.get("images") or []
            cat_agg[cat]["images"] += len(imgs)
            for im in imgs:
                im_str = str(im).strip()
                if im_str.startswith("//"):
                    full_src = "https:" + im_str
                elif im_str.startswith("/"):
                    full_src = "https://www.fenalco.com.co" + im_str
                elif not im_str.startswith("http"):
                    full_src = "https://www.fenalco.com.co/" + im_str
                else:
                    full_src = im_str
                self._imgs.append({
                    "src": full_src,
                    "raw_src": im_str,
                    "article_title": r.get("title") or "Sin título",
                    "article_url": r.get("url") or "",
                    "category": cat,
                    "date": r.get("publish_date") or "",
                    "kind": r.get("kind") or "",
                })

        self._cat_stats = sorted(cat_agg.values(), key=lambda x: -x["records"])

    def get_all_documents(self, search: str = "") -> list:
        if not search or not search.strip():
            return self._docs
        q = search.lower().strip()
        return [
            d for d in self._docs
            if q in d["filename"].lower() or q in d["article_title"].lower() or q in d["category"].lower()
        ]

    def get_all_images(self, search: str = "") -> list:
        if not search or not search.strip():
            return self._imgs
        q = search.lower().strip()
        return [
            im for im in self._imgs
            if q in im["article_title"].lower() or q in im["category"].lower() or q in im["raw_src"].lower()
        ]

    def get_category_stats(self, search: str = "") -> list:
        if not search or not search.strip():
            return self._cat_stats
        q = search.lower().strip()
        return [c for c in self._cat_stats if q in c["category"].lower()]

    # ------------------------------------------------------------- DataFrame
    @staticmethod
    def _build_frame(records: list) -> pd.DataFrame:
        rows = []
        for r in records:
            txt = r.get("content_text") or ""
            rows.append({
                "url": r.get("url", ""),
                "kind": r.get("kind", ""),
                "tipo": KIND_LABELS.get(r.get("kind"), r.get("kind", "")),
                "category": r.get("category", ""),
                "title": r.get("title", "") or "",
                "subtitle": r.get("subtitle", "") or "",
                "publish_date": r.get("publish_date", "") or "",
                "lastmod": r.get("lastmod", "") or "",
                "image": r.get("image", "") or "",
                "text_chars": len(txt),
                "num_blocks": len(r.get("content_blocks") or []),
                "n_documents": len(r.get("documents") or []),
                "n_images": len(r.get("images") or []),
            })
        df = pd.DataFrame(rows).sort_values("publish_date", ascending=False)
        df = df.reset_index(drop=True)
        return df

    # ------------------------------------------------------------ metadata
    @property
    def categories(self) -> list:
        return sorted(self.df["category"].dropna().unique().tolist())

    def stats(self) -> dict:
        return {
            "total": int(len(self.df)),
            "posts": int((self.df["kind"] == "blog-post").sum()),
            "cms": int((self.df["kind"] == "cms").sum()),
            "eventos": int((self.df["kind"] == "event").sum()),
            "documentos": int(self.df["n_documents"].sum()),
            "imagenes": int(self.df["n_images"].sum()),
            "caracteres": int(self.df["text_chars"].sum()),
            "categorias": len(self.categories),
        }

    # ------------------------------------------------------------ consulta
    def query(self, search="", kinds=None, categories=None,
              date_from=None, date_to=None,
              only_docs=False, only_images=False) -> pd.DataFrame:
        """Devuelve un DataFrame filtrado según los criterios recibidos."""
        df = self.df.copy()

        if search and search.strip():
            scores = self.search_engine.search_scores(search)
            if scores:
                df = df[df["url"].isin(scores)].copy()
                df["_score"] = df["url"].map(scores)
                df = df.sort_values(by=["_score", "publish_date"], ascending=[False, False])
            else:
                df = df.iloc[0:0].copy()

        if kinds:
            kinds = {_TIPO.get(k, k) for k in kinds}
            df = df[df["kind"].isin(kinds)]

        if categories:
            df = df[df["category"].isin(categories)]

        if date_from:
            df = df[df["publish_date"] >= date_from]
        if date_to:
            df = df[df["publish_date"] <= date_to]

        if only_docs:
            df = df[df["n_documents"] > 0]

        if only_images:
            df = df[df["n_images"] > 0]

        return df.reset_index(drop=True)

    def _text_of(self, url: str) -> str:
        r = self.by_url.get(url)
        return (r.get("content_text") or "") if r else ""

    # ------------------------------------------------------------- helpers
    def order(self, df: pd.DataFrame, sort_by) -> pd.DataFrame:
        if not sort_by:
            return df
        for _s in sort_by:
            col = _s.get("column_id")
            asc = not (_s.get("direction") == "desc")
            if col in df.columns:
                df = df.sort_values(col, ascending=asc, kind="mergesort")
        return df.reset_index(drop=True)

    def row_to_jsonl(self, url: str) -> str:
        r = self.by_url.get(url)
        return json.dumps(r, ensure_ascii=False) if r else ""

    def record(self, url: str) -> dict | None:
        if not url:
            return None
        rec = self.by_url.get(url)
        if rec:
            return rec
        if url.endswith("/"):
            return self.by_url.get(url[:-1])
        return self.by_url.get(url + "/")
