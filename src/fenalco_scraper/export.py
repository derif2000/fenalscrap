"""Convierte el JSONL de registros en entregables finales legibles y en CSV."""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import config


def load_records(path: Path = None) -> list:
    path = path or config.RECORDS_FILE
    records = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _slug(title: str, url: str) -> str:
    from urllib.parse import unquote
    base = url.rstrip("/").split("/")[-1]
    base = unquote(base)
    return base if base and base != "info" else "pagina"


def blocks_to_markdown(blocks: list) -> str:
    out = []
    for b in blocks:
        t = b["type"]
        if t == "heading":
            out.append(f"{'#' * b['level']} {b['text']}")
        elif t == "paragraph":
            out.append(b["text"])
        elif t == "quote":
            out.append(f"> {b['text']}")
        elif t == "list":
            mark = "- " if not b["ordered"] else "1. "
            for it in b["items"]:
                out.append(f"{mark}{it}")
        elif t == "image":
            src = b.get("src") or ""
            cap = b.get("caption") or b.get("alt") or ""
            if src:
                out.append("![" + cap + "](" + src + ")")
            if cap:
                out.append("*" + cap + "*")
        elif t == "table":
            for r in b["rows"]:
                out.append("| " + " | ".join(r) + " |")
    return "\n\n".join(out)


def export(output_dir: Path = None) -> dict:
    output_dir = output_dir or config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    records = load_records()
    if not records:
        print("[export] No hay registros todavía (ejecuta primero el scrape).")
        return {}

    # 1) JSON consolidado
    all_json = output_dir / "fenalco_all.json"
    all_json.write_text(json.dumps(records, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # 2) CSV plano
    csv_file = output_dir / "fenalco_index.csv"
    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["url", "kind", "category", "title", "publish_date",
                    "lastmod", "image", "text_chars", "num_blocks",
                    "n_images", "n_documents"])
        for r in records:
            w.writerow([
                r["url"], r["kind"], r["category"], r["title"],
                r["publish_date"], r["lastmod"], r["image"],
                len(r["content_text"]), len(r["content_blocks"]),
                len(r["images"]), len(r["documents"]),
            ])

    # 3) Markdown por categoría
    md_root = output_dir / "markdown"
    md_root.mkdir(parents=True, exist_ok=True)
    grouped = defaultdict(list)
    for r in records:
        grouped[r["category"]].append(r)

    md_files = {}
    for cat, recs in grouped.items():
        safe = cat.replace("/", "_").strip() or "Sin-categoria"
        path = md_root / f"{safe}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {safe}\n\nTotal: {len(recs)}\n\n")
            for r in recs:
                f.write(f"## {r['title'] or r['url']}\n\n")
                f.write(f"- URL: {r['url']}\n")
                if r["publish_date"]:
                    f.write(f"- Fecha: {r['publish_date']}\n")
                if r["subtitle"]:
                    f.write(f"- Resumen: {r['subtitle']}\n")
                f.write("\n")
                f.write(blocks_to_markdown(r["content_blocks"]))
                f.write("\n\n---\n\n")
        md_files[safe] = str(path)

    # 4) Resumen
    stats = Counter(r["kind"] for r in records)
    cat_stats = Counter(r["category"] for r in records)
    summary = {
        "total_pages": len(records),
        "por_tipo": dict(stats),
        "por_categoria": dict(cat_stats.most_common()),
        "archivos": {
            "json": str(all_json),
            "csv": str(csv_file),
            "markdown": md_files,
        },
    }
    (output_dir / "resumen.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[export] {len(records)} registros exportados a {output_dir}")
    return summary