#!/usr/bin/env python
"""Genera los entregables finales (JSON, CSV, Markdown) desde el JSONL scrapeado.

Uso: python export.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fenalco_scraper import config                    # noqa: E402
from fenalco_scraper.export import export             # noqa: E402


def main():
    summary = export(config.OUTPUT_DIR)
    if summary:
        import json as _json
        print(_json.dumps(summary["por_tipo"], ensure_ascii=False))
        print("Archivos generados:")
        for k, v in summary["archivos"].items():
            if isinstance(v, dict):
                print(f"  {k}/")
                for c, p in v.items():
                    print(f"    - {c}: {p}")
            else:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()