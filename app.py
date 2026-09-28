#!/usr/bin/env python
"""Aplicación web de consulta de los datos públicos de FENALCO.

Uso:
    python app.py                # abre http://127.0.0.1:8050
    python app.py --port 8051    # puerto personalizado
"""
import argparse
import sys
from pathlib import Path

import dash_bootstrap_components as dbc
from dash import Dash, dcc, html

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from webapp import data as data_mod              # noqa: E402
from webapp.callbacks import register_callbacks  # noqa: E402
from webapp.layout import build_layout           # noqa: E402

# Estilos y tema
EXTERNAL_STYLES = [
    dbc.themes.MINTY,
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css",
]

CUSTOM_CSS = """
:root {
  --fenalco-blue: #0b5cab;
}
body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
.navbar.bg-primary { background: linear-gradient(90deg, #084a86, #0b5cab) !important; }
.card { border-radius: .65rem; }
#main-table .dash-spreadsheet-container .dash-spreadsheet-inner th {
  background: rgba(11,92,171,.07) !important;
  color: #0b3a66 !important;
}
.fenalco-content { line-height: 1.6; font-size: 14.5px; }
.fenalco-thumb { width: 72px; height: 72px; object-fit: cover; }
.dash-table-tooltip {
  max-width: 420px; white-space: normal; z-index: 1000;
}
.fen-metric-icon { font-size: 1.5rem; }

/* Asistente de IA */
.assistant-chat {
  max-height: 340px; overflow-y: auto; padding-right: 4px;
}
.assistant-bubble {
  padding: .5rem .75rem; border-radius: .75rem; font-size: 14px;
}
.assistant-bubble.user {
  background: var(--bs-primary); color: #fff; border-top-right-radius: .2rem;
}
.assistant-bubble.ai {
  background: #f1f3f5; color: #212529; border-top-left-radius: .2rem;
}
.assistant-sources {
  border-left: 3px solid var(--bs-primary); padding-left: .5rem;
}

/* Modal de lectura de documento */
#doc-modal .modal-dialog {
  max-width: 1150px;
}
#doc-modal .modal-content {
  background: #fff;
  border-radius: .8rem;
}
#doc-modal .modal-body {
  background: #fff;
  color: #212529;
}
#doc-modal .fenalco-content {
  font-size: 16px;
  line-height: 1.7;
  color: #212529;
}
#doc-modal h1, #doc-modal h2, #doc-modal h3 {
  color: #0b3a66;
}
/* Botones de fuente del asistente más claros */
.assistant-source-btn {
  white-space: normal;
  overflow-wrap: anywhere;
}
/* Miniaturas de imágenes extraídas de los PDFs (gráficas) */
.assistant-doc-img {
  max-width: 180px;
  max-height: 120px;
  object-fit: contain;
  border: 2px solid rgba(11,92,171,.35);
  border-radius: .45rem;
  transition: transform .15s ease, box-shadow .15s ease;
  cursor: pointer;
}
.assistant-doc-img:hover {
  transform: scale(1.04);
  box-shadow: 0 .35rem .9rem rgba(11,92,171,.25);
}
.assistant-img-btn {
  border: none;
  background: transparent;
  padding: 0;
  display: inline-block;
}

/* Tarjetas de métricas interactivas */
.metric-card-interactive {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  user-select: none;
  border: 1px solid rgba(0,0,0,0.06);
}
.metric-card-interactive:hover {
  transform: translateY(-3px);
  box-shadow: 0 0.5rem 1.25rem rgba(11,92,171,.18) !important;
  border-color: rgba(11,92,171,.4) !important;
}
.metric-card-interactive:active {
  transform: translateY(-1px);
}

/* Galería de imágenes */
.gallery-img-card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  border-radius: 0.65rem;
  overflow: hidden;
  border: 1px solid rgba(0,0,0,0.08);
}
.gallery-img-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 0.5rem 1.2rem rgba(0,0,0,0.14) !important;
  border-color: rgba(11,92,171,.4) !important;
}
.gallery-thumb-container {
  height: 180px;
  background-color: #f8f9fa;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.gallery-thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.25s ease;
}
.gallery-img-card:hover .gallery-thumb-img {
  transform: scale(1.04);
}

/* Lista de adjuntos */
.doc-item-card {
  transition: background-color 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
  border-radius: 0.5rem;
  border: 1px solid rgba(0,0,0,0.07);
}
.doc-item-card:hover {
  background-color: #f8fbfe !important;
  border-color: rgba(11,92,171,.35) !important;
  transform: translateX(2px);
}

/* Catálogo de categorías */
.cat-pill-card {
  transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
  cursor: pointer;
  border-radius: 0.6rem;
  border: 1px solid rgba(0,0,0,0.08);
}
.cat-pill-card:hover {
  transform: translateY(-2px);
  border-color: var(--bs-primary) !important;
  box-shadow: 0 0.4rem 0.9rem rgba(11,92,171,.12);
  background-color: #f8fbfe;
}

/* Buscador de Cifras */
.cifra-mark {
  background-color: #fff3cd !important;
  color: #664d03 !important;
  border: 1px solid #ffe69c;
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-weight: 700;
}
.cifra-result-card {
  transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
  border: 1px solid rgba(0,0,0,0.08) !important;
  border-radius: 0.65rem;
}
.cifra-result-card:hover {
  transform: translateY(-2px);
  border-color: rgba(11,92,171,.3) !important;
  box-shadow: 0 0.4rem 1rem rgba(11,92,171,.1) !important;
}
.cifra-snippet-text {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
}

/* Indicador de estado de IA en la navbar */
.ai-status-badge {
  transition: opacity 0.2s ease;
  color: #fff;
  user-select: none;
}
.ai-status-badge:hover { opacity: 0.85; }
.ai-status-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}
.ai-status-ok {
  background: #4ade80;
  box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7);
  animation: ai-pulse-ok 2.2s ease-in-out infinite;
}
.ai-status-err {
  background: #f87171;
  box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.7);
  animation: ai-pulse-err 2.2s ease-in-out infinite;
}
@keyframes ai-pulse-ok {
  0%   { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0.7); }
  70%  { box-shadow: 0 0 0 6px rgba(74, 222, 128, 0); }
  100% { box-shadow: 0 0 0 0 rgba(74, 222, 128, 0); }
}
@keyframes ai-pulse-err {
  0%   { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0.7); }
  70%  { box-shadow: 0 0 0 6px rgba(248, 113, 113, 0); }
  100% { box-shadow: 0 0 0 0 rgba(248, 113, 113, 0); }
}

/* Estilo especial para líneas de atribución de origen (📍 Origen de la cifra:)
   El modelo las genera dentro de párrafos markdown. Se destacan visualmente. */
.assistant-bubble.ai p:has(> strong:first-child):has(em) {
  /* no aplica específicamente aquí */
}
/* Cualquier párrafo que empiece con "📍" se resalta */
.assistant-bubble.ai p:first-of-type:not(:last-child),
.assistant-bubble.ai p {
  margin-bottom: 0.4rem;
}
/* Párrafos de atribución: se detectan por el emoji 📍 vía JS no disponible en Dash,
   por eso usamos un blockquote o simplemente mejorar la tipografía del bloque */
.assistant-bubble.ai blockquote {
  border-left: 4px solid #0b5cab;
  background: rgba(11,92,171,.06);
  border-radius: 0 .4rem .4rem 0;
  padding: .4rem .7rem;
  margin: .5rem 0;
  font-size: 13px;
  color: #0b3a66;
}
/* Estilo para citas [1], [2] en el texto del asistente */
.assistant-bubble.ai code {
  background: rgba(11,92,171,.1);
  color: #0b3a66;
  border-radius: 3px;
  padding: 1px 4px;
  font-size: 12px;
}
"""


def create_app():
    store = data_mod.FenalcoData()

    from webapp.assistant import Assistant as _Assistant

    app = Dash(
        __name__,
        external_stylesheets=EXTERNAL_STYLES,
        suppress_callback_exceptions=True,
        title="FENALCO · Centro de Datos Públicos",
        update_title="Cargando…",
    )

    def serve_layout():
        _tmp_assistant = _Assistant(store)
        _ai_status = _tmp_assistant.ai_status()
        return html.Div([
            build_layout(store.categories, store.stats(), ai_status=_ai_status),
            dcc.Markdown(f"<style>{CUSTOM_CSS}</style>",
                         dangerously_allow_html=True),
        ])

    app.layout = serve_layout

    # Sirve las imágenes extraídas de los PDFs (p. ej. gráficas) para que el
    # asistente pueda incrustarlas y abrirlas en pantalla completa.
    from webapp.drive_reader import _IMGS_DIR
    from flask import abort, send_file

    @app.server.route("/doc-img/<doc_id>/<filename>")
    def _serve_doc_image(doc_id, filename):
        img_path = Path(_IMGS_DIR) / doc_id / filename
        if img_path.is_file():
            return send_file(str(img_path))
        abort(404)

    register_callbacks(app, store)
    return app


# Instancia expuesta para servidores WSGI (Gunicorn en Render: `app:server`)
app = create_app()
server = app.server


def main():
    import os
    p = argparse.ArgumentParser(description="Interfaz web de datos FENALCO")
    p.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8050)))
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    print("=" * 60)
    print("  FENALCO · Centro de Datos Públicos")
    print(f"  Abre:  http://{args.host}:{args.port}")
    print("  Ctrl+C para detener.")
    print("=" * 60)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()