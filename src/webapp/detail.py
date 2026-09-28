"""Construye el panel de detalle (tarjetas, documento, media) de un registro."""

import dash_bootstrap_components as dbc
from dash import dcc, html


def blocks_to_markdown(blocks: list) -> str:
    """Convierte content_blocks a texto Markdown."""
    out = []
    for b in blocks:
        t = b.get("type")
        text = (b.get("text") or "").strip()
        if t == "heading":
            out.append(f"{'#' * int(b.get('level', 2))} {text}")
        elif t == "paragraph":
            out.append(text)
        elif t == "quote":
            out.append(f"> {text}")
        elif t == "list":
            mark = "- " if not b.get("ordered") else "1. "
            for item in b.get("items", []):
                out.append(f"{mark}{item}")
        elif t == "image":
            src = b.get("src") or ""
            cap = (b.get("caption") or b.get("alt") or "").strip()
            if src:
                out.append(f"![{cap}]({src})")
            if cap:
                out.append(f"*{cap}*")
        elif t == "table":
            for row in b.get("rows", []):
                out.append("| " + " | ".join(row) + " |")
    return "\n\n".join(out).strip()


def _badge(text: str, color: str) -> dbc.Badge:
    return dbc.Badge(text, color=color, className="me-1", pill=True)


def _meta_item(label: str, value, href: str = None) -> html.Div:
    if href:
        value_el = html.A(value, href=href, target="_blank",
                          className="text-break")
    else:
        value_el = html.Span(value, className="text-break")
    return html.Div([
        html.Span(f"{label}: ", className="fw-bold text-secondary"),
        value_el,
    ], className="mb-1 small")


def build_detail(record: dict, is_modal: bool = False, existing_summary: str = None) -> dbc.Card:
    """Devuelve la tarjeta de detalle completa para el registro dado.

    Args:
        record: Diccionario con los datos del registro.
        is_modal: Si True, usa IDs de modal para el botón y salida de resumen IA.
        existing_summary: Texto de resumen existente si ya fue generado para este registro.
    """
    if not record:
        return dbc.Alert("Haz clic en una fila de la tabla para ver su detalle.",
                         color="info", className="shadow-sm")

    kind = record.get("kind", "")
    color = {"blog-post": "primary", "cms": "success", "event": "warning"}.get(kind, "secondary")
    tipo_label = {"blog-post": "Blog / Noticia", "cms": "Página / CMS", "event": "Evento"}.get(kind, kind)
    blocks = record.get("content_blocks") or []
    text = record.get("content_text") or ""

    header = dbc.CardHeader([
        html.Div([
            _badge(tipo_label, color),
            _badge(record.get("category") or "—", "secondary"),
        ]),
        html.H5(record.get("title") or "(sin título)", className="mt-2 mb-0"),
    ], style={"backgroundColor": "var(--bs-light)"})

    body_children = []

    if record.get("subtitle"):
        body_children.append(html.P(record.get("subtitle"),
                                    className="fst-italic text-muted small"))

    # Metadatos
    meta = []
    if record.get("publish_date"):
        meta.append(_meta_item("Fecha", record["publish_date"]))
    if record.get("lastmod"):
        meta.append(_meta_item("Última modificación", record["lastmod"]))
    meta.append(_meta_item("Longitud del texto", f"{len(text):,} caracteres"))
    meta.append(_meta_item("Bloques", str(len(blocks))))
    meta.append(_meta_item("Imágenes", str(len(record.get("images") or []))))
    meta.append(_meta_item("Documentos", str(len(record.get("documents") or []))))
    meta.append(_meta_item("Enlace", record.get("url", ""),
                           record.get("url")))
    body_children.append(html.Div(meta, className="mb-3"))

    # Contenido
    if text:
        body_children.append(html.H6("Contenido", className="mt-3 fw-bold text-uppercase text-secondary"))
        body_children.append(dbc.Card([
            dbc.CardBody(
                dcc_markdown_safe(blocks_to_markdown(blocks) or text),
                className="fenalco-content")
        ], className="border-0 bg-light"))

    # Documentos
    docs = record.get("documents") or []
    if docs:
        from .drive_reader import clean_spaced_name, extract_drive_id, drive_reader
        body_children.append(html.H6(f"Documentos / Adjuntos ({len(docs)})",
                                     className="mt-3 fw-bold text-uppercase text-secondary"))
        for d in docs[:20]:
            raw_fn = d.get("filename") or ""
            cfn = clean_spaced_name(raw_fn) or "Documento adjunto"
            u = d.get("url") or ""
            did = extract_drive_id(u)
            cached_text = drive_reader.get_cached_text(did) if did else None
            is_drive = bool(did) or "drive.google" in u or "docs.google" in u

            doc_item_children = [
                html.I(className="bi bi-google text-danger me-1" if is_drive else "bi bi-file-earmark-text me-1 text-secondary"),
                html.A(cfn, href=u, target="_blank", className="text-break fw-medium"),
            ]
            if is_drive:
                doc_item_children.append(dbc.Badge("Google Drive", color="light", text_color="danger", className="ms-2 border small"))

            if cached_text:
                doc_item_children.append(dbc.Badge("Texto analizado", color="success", className="ms-1 small"))
                doc_item_children.append(
                    html.Details([
                        html.Summary("Ver texto extraído del documento", className="small text-primary mt-1 cursor-pointer"),
                        html.Pre(cached_text[:3500] + ("\n... [contenido truncado]" if len(cached_text) > 3500 else ""),
                                 className="p-2 bg-light border rounded small text-wrap mt-1",
                                 style={"maxHeight": "200px", "overflowY": "auto", "fontSize": "11px", "whiteSpace": "pre-wrap"}),
                    ], className="mt-1")
                )

            body_children.append(html.Div(doc_item_children, className="mb-2 p-2 border-bottom"))


    # Imágenes
    imgs = record.get("images") or []
    if imgs:
        body_children.append(html.H6(f"Imágenes ({len(imgs)})",
                                     className="mt-3 fw-bold text-uppercase text-secondary"))
        body_children.append(html.Div([
            html.Img(src=i, className="fenalco-thumb img-thumbnail me-2 mb-2")
            for i in imgs[:12]
        ]))

    # ---- Resumen IA ----
    # Disponible tanto en el panel lateral como en el modal de lectura completa.
    if bool(text or (record.get("documents") or [])):
        from .layout import IDs
        btn_id = IDs.SUMM_MODAL_BTN if is_modal else IDs.SUMM_BTN
        out_id = IDs.SUMM_MODAL_OUT if is_modal else IDs.SUMM_OUT

        summary_children = render_summary_card(existing_summary) if existing_summary else None

        body_children.append(html.Hr(className="my-3"))
        body_children.append(html.Div([
            html.H6([
                html.I(className="bi bi-stars me-2 text-warning"),
                "Resumen IA",
            ], className="fw-bold text-uppercase text-secondary mb-2"),
            dbc.Button(
                [html.I(className="bi bi-magic me-2"),
                 "Resumir con IA" if not existing_summary else "Volver a resumir con IA"],
                id=btn_id,
                color="warning",
                outline=True,
                size="sm",
                n_clicks=0,
                className="mb-2",
            ),
            dbc.Spinner(
                html.Div(id=out_id, children=summary_children, className="mt-2"),
                color="warning",
                size="sm",
            ),
        ], className="summ-ia-section"))

    return dbc.Card([header, dbc.CardBody(body_children)],
                    className="shadow-sm h-100")


def render_summary_card(summary: str):
    if not summary:
        return None
    return dbc.Card([
        dbc.CardHeader([
            html.I(className="bi bi-stars me-2 text-warning"),
            html.Span("Resumen generado por IA", className="fw-semibold small"),
        ], className="py-2 px-3", style={"backgroundColor": "rgba(255,193,7,.08)"}),
        dbc.CardBody(
            dcc_markdown_safe(summary),
            className="fenalco-content p-3",
            style={"fontSize": "13.5px"},
        ),
    ], className="border-warning border-opacity-50 shadow-none")


def dcc_markdown_safe(text: str):
    return dcc.Markdown(text, dangerously_allow_html=False,
                        link_target="_blank")

